"""IMD 0.25° gridded daily rainfall ingestion (SPEC F03, §3.3, §6.2).

Wraps `imdlib` (downloads IMD Pune's binary grids) and converts each year to
the long-format `rain_grid` Parquet schema: date, lat, lon, rain_mm,
product_version, raw_sha256. Ocean/no-data cells (NaN in the source grid)
are dropped rather than stored. Raw `.grd` files are left where imdlib
writes them — content-addressed by SHA-256 for provenance, never
overwritten — and that hash is fetched into every row via `raw_sha256`.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import imdlib
import polars as pl

from mq.pipelines.dq import (
    DQCheckResult,
    DQGateFailedError,
    dq01_missing_dates,
    dq02_duplicate_keys,
    dq03_value_range,
    dq04_schema_drift,
    gate,
    persist_results,
)
from mq.specs.sources import sha256_of

IMD_PRODUCT_VERSION = "imdlib-0.25deg-v1"
IMD_REALTIME_PRODUCT_VERSION = "imdlib-0.25deg-realtime-v1"

RAW_DIR = Path("data/raw/imd")
REALTIME_RAW_DIR = Path("data/raw/imd_realtime")
PARQUET_DIR = Path("data/parquet/rain_grid")
REALTIME_PARQUET_DIR = Path("data/parquet/rain_grid_realtime")

RAIN_GRID_COLUMNS = ["date", "lat", "lon", "rain_mm", "product_version", "raw_sha256"]

RAIN_GRID_EXPECTED_SCHEMA: dict[str, pl.DataType] = {
    "date": pl.Date(),
    "lat": pl.Float64(),
    "lon": pl.Float64(),
    "rain_mm": pl.Float64(),
    "product_version": pl.String(),
    "raw_sha256": pl.String(),
}


def run_rain_grid_dq(df: pl.DataFrame, *, year: int) -> list[DQCheckResult]:
    dataset = f"rain_grid:imd:{year}"
    return [
        dq01_missing_dates(
            df,
            date_col="date",
            dataset=dataset,
            expected_start=date(year, 1, 1),
            expected_end=date(year, 12, 31),
        ),
        dq02_duplicate_keys(df, key_cols=["date", "lat", "lon"], dataset=dataset),
        dq03_value_range(df, value_col="rain_mm", dataset=dataset, lo=0.0, hi=1000.0),
        dq04_schema_drift(df, expected_schema=RAIN_GRID_EXPECTED_SCHEMA, dataset=dataset),
    ]


def fetch_imd_rain_year(year: int, *, raw_dir: Path = RAW_DIR) -> pl.DataFrame:
    """Download (or reuse the cached) IMD daily rainfall grid for `year`,
    returning it in the long rain_grid schema with ocean/no-data cells
    dropped."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    imd_obj = imdlib.get_data("rain", year, year, fn_format="yearwise", file_dir=str(raw_dir))
    ds = imd_obj.get_xarray()
    df = ds.to_dataframe().reset_index()

    raw_file_path = raw_dir / "rain" / f"{year}.grd"
    digest = sha256_of(raw_file_path) if raw_file_path.exists() else ""

    pl_df = pl.from_pandas(df).rename({"time": "date", "rain": "rain_mm"})
    pl_df = pl_df.filter(pl.col("rain_mm").is_not_null()).with_columns(
        pl.col("date").cast(pl.Date),
        pl.lit(IMD_PRODUCT_VERSION).alias("product_version"),
        pl.lit(digest).alias("raw_sha256"),
    )
    return pl_df.select(RAIN_GRID_COLUMNS)


def run_rain_grid_dq_range(
    df: pl.DataFrame, *, dataset: str, start: date, end: date
) -> list[DQCheckResult]:
    """Like run_rain_grid_dq but for an arbitrary (not full-year) date range
    — used for the near-real-time product."""
    return [
        dq01_missing_dates(
            df, date_col="date", dataset=dataset, expected_start=start, expected_end=end
        ),
        dq02_duplicate_keys(df, key_cols=["date", "lat", "lon"], dataset=dataset),
        dq03_value_range(df, value_col="rain_mm", dataset=dataset, lo=0.0, hi=1000.0),
        dq04_schema_drift(df, expected_schema=RAIN_GRID_EXPECTED_SCHEMA, dataset=dataset),
    ]


def fetch_imd_rain_realtime(
    start: date, end: date, *, raw_dir: Path = REALTIME_RAW_DIR
) -> pl.DataFrame:
    """Download (or reuse the cached) IMD near-real-time daily rainfall grid
    for [start, end], returning it in the long rain_grid schema. This is a
    separate, lower-latency product from the finalized historical archive
    (`fetch_imd_rain_year`) — it's what gives the ledger genuine
    observed-to-date rainfall for the current, in-progress season."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    imd_obj = imdlib.get_real_data(
        "rain", start.isoformat(), end.isoformat(), file_dir=str(raw_dir)
    )
    ds = imd_obj.get_xarray()
    df = ds.to_dataframe().reset_index()
    pl_df = pl.from_pandas(df).rename({"time": "date", "rain": "rain_mm"})
    pl_df = pl_df.filter(pl.col("rain_mm").is_not_null()).with_columns(
        pl.col("date").cast(pl.Date), pl.lit(IMD_REALTIME_PRODUCT_VERSION).alias("product_version")
    )

    # Real-time files are one-per-day (rain_ind0.25_YY_MM_DD.grd) — hash each
    # day's own file rather than one hash for the whole fetch.
    digest_by_date = {}
    d = start
    while d <= end:
        day_file = raw_dir / f"rain_ind0.25_{d.strftime('%y_%m_%d')}.grd"
        digest_by_date[d] = sha256_of(day_file) if day_file.exists() else ""
        d += timedelta(days=1)
    digest_df = pl.DataFrame(
        {"date": list(digest_by_date.keys()), "raw_sha256": list(digest_by_date.values())}
    ).with_columns(pl.col("date").cast(pl.Date))
    pl_df = pl_df.join(digest_df, on="date", how="left")
    return pl_df.select(RAIN_GRID_COLUMNS)


def write_rain_grid_realtime(
    start: date,
    end: date,
    *,
    raw_dir: Path = REALTIME_RAW_DIR,
    parquet_dir: Path = REALTIME_PARQUET_DIR,
) -> Path:
    """Fetch near-real-time IMD rainfall for [start, end], run the DQ gate,
    and write it to Parquet partitioned by the end date's year. Raises
    DQGateFailedError and writes nothing if any check fails."""
    df = fetch_imd_rain_realtime(start, end, raw_dir=raw_dir)
    dataset = f"rain_grid_realtime:imd:{start.isoformat()}_{end.isoformat()}"
    results = run_rain_grid_dq_range(df, dataset=dataset, start=start, end=end)
    persist_results(results)
    if not gate(results):
        raise DQGateFailedError([r for r in results if r.status == "fail"])

    out_dir = parquet_dir / "source=imd_realtime" / f"year={end.year}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{start.isoformat()}_{end.isoformat()}.parquet"
    df.write_parquet(out_path)
    return out_path


def write_rain_grid_year(
    year: int, *, raw_dir: Path = RAW_DIR, parquet_dir: Path = PARQUET_DIR
) -> Path:
    """Fetch (or reuse) one year of IMD rainfall, run the DQ01-DQ04 gate,
    persist the DQ results, and — only if the gate passes — write it to the
    partitioned Parquet dataset (`source=imd/year=<year>`). Raises
    DQGateFailedError and does not write anything if any check fails."""
    df = fetch_imd_rain_year(year, raw_dir=raw_dir)
    results = run_rain_grid_dq(df, year=year)
    persist_results(results)
    if not gate(results):
        raise DQGateFailedError([r for r in results if r.status == "fail"])

    out_dir = parquet_dir / "source=imd" / f"year={year}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "rain_grid.parquet"
    df.write_parquet(out_path)
    return out_path
