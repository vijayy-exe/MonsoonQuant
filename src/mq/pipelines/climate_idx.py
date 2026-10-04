"""ONI / DMI / MJO climate-driver ingestion (SPEC F04, §3.3, §6.2).

Each source is a small public text file with no explicit per-row
publication timestamp, so `release_date` is set to the ingestion run's own
date — the date we can prove we actually held the value, never earlier.
That keeps every downstream as_of filter honest (SPEC §0.4-3: no
look-ahead) even though it under-uses data that may have been available a
day or two earlier.

Output is the long-format `climate_idx` Parquet schema (SPEC §6.2):
index, date, value, release_date — partitioned by `index=`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import requests

from mq.pipelines.dq import DQCheckResult, dq02_duplicate_keys, dq04_schema_drift

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
DMI_URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"
MJO_URL = "https://www.bom.gov.au/climate/mjo/graphics/rmm.74toRealtime.txt"

# BoM blocks requests with no browser-like User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (research script; MonsoonQuant; +https://github.com)"}

PARQUET_DIR = Path("data/parquet/climate_idx")

CLIMATE_IDX_EXPECTED_SCHEMA: dict[str, pl.DataType] = {
    "index": pl.String(),
    "date": pl.Date(),
    "value": pl.Float64(),
    "release_date": pl.Date(),
}

# ONI's running 3-month seasons, mapped to their middle calendar month.
_ONI_SEASON_MONTH = {
    "DJF": 1,
    "JFM": 2,
    "FMA": 3,
    "MAM": 4,
    "AMJ": 5,
    "MJJ": 6,
    "JJA": 7,
    "JAS": 8,
    "ASO": 9,
    "SON": 10,
    "OND": 11,
    "NDJ": 12,
}


def fetch_oni(*, release_date: date | None = None) -> pl.DataFrame:
    """NOAA CPC Oceanic Nino Index (3-month running SST anomaly)."""
    release_date = release_date or datetime.now(UTC).date()
    text = requests.get(ONI_URL, headers=_HEADERS, timeout=30).text
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) != 4:
            continue
        season, year_str, _total, anom = parts
        if season not in _ONI_SEASON_MONTH:
            continue
        rows.append(
            {
                "index": "oni",
                "date": date(int(year_str), _ONI_SEASON_MONTH[season], 15),
                "value": float(anom),
                "release_date": release_date,
            }
        )
    return pl.DataFrame(rows, schema=CLIMATE_IDX_EXPECTED_SCHEMA)


def fetch_dmi(*, release_date: date | None = None) -> pl.DataFrame:
    """NOAA PSL Dipole Mode Index (IOD), monthly."""
    release_date = release_date or datetime.now(UTC).date()
    text = requests.get(DMI_URL, headers=_HEADERS, timeout=30).text
    rows = []
    for line in text.splitlines()[1:]:  # line 0 is "start_year end_year"
        parts = line.split()
        if len(parts) != 13 or not parts[0].isdigit():
            break  # reached the trailer ("-9999" + metadata text)
        year = int(parts[0])
        for month, raw_value in enumerate(parts[1:], start=1):
            value = float(raw_value)
            if value <= -999:  # sentinel for missing (-9999.000)
                continue
            rows.append(
                {
                    "index": "dmi",
                    "date": date(year, month, 15),
                    "value": value,
                    "release_date": release_date,
                }
            )
    return pl.DataFrame(rows, schema=CLIMATE_IDX_EXPECTED_SCHEMA)


def fetch_mjo(*, release_date: date | None = None) -> pl.DataFrame:
    """BoM RMM MJO index, daily: rmm1, rmm2, phase, amplitude (long format,
    one row per sub-index)."""
    release_date = release_date or datetime.now(UTC).date()
    text = requests.get(MJO_URL, headers=_HEADERS, timeout=30).text
    rows = []
    for line in text.splitlines()[2:]:  # first 2 lines are header text
        parts = line.split()
        if len(parts) < 7:
            continue
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        rmm1, rmm2, phase, amplitude = (float(p) for p in parts[3:7])
        if abs(rmm1) >= 999 or abs(rmm2) >= 999:  # missing-value sentinel
            continue
        d = date(year, month, day)
        rows.extend(
            [
                {"index": "mjo_rmm1", "date": d, "value": rmm1, "release_date": release_date},
                {"index": "mjo_rmm2", "date": d, "value": rmm2, "release_date": release_date},
                {"index": "mjo_phase", "date": d, "value": phase, "release_date": release_date},
                {
                    "index": "mjo_amplitude",
                    "date": d,
                    "value": amplitude,
                    "release_date": release_date,
                },
            ]
        )
    return pl.DataFrame(rows, schema=CLIMATE_IDX_EXPECTED_SCHEMA)


def run_climate_idx_dq(df: pl.DataFrame, *, dataset: str) -> list[DQCheckResult]:
    return [
        dq02_duplicate_keys(df, key_cols=["index", "date"], dataset=dataset),
        dq04_schema_drift(df, expected_schema=CLIMATE_IDX_EXPECTED_SCHEMA, dataset=dataset),
    ]


def write_climate_idx(df: pl.DataFrame, *, parquet_dir: Path = PARQUET_DIR) -> list[Path]:
    """Write a long-format climate_idx dataframe, partitioned by `index=`.
    Appends to (rather than overwrites) any existing partition file,
    de-duplicating on (index, date) and keeping the latest release_date —
    later ingestion runs of the same historical row are *revisions*, kept
    as the newest observation, never silently discarded (SPEC DQ08)."""
    out_paths = []
    for index_name, part in df.partition_by("index", as_dict=True).items():
        name = index_name[0] if isinstance(index_name, tuple) else index_name
        out_dir = parquet_dir / f"index={name}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "data.parquet"
        if out_path.exists():
            existing = pl.read_parquet(out_path)
            part = (
                pl.concat([existing, part])
                .sort("release_date")
                .unique(subset=["index", "date"], keep="last")
                .sort("date")
            )
        part.write_parquet(out_path)
        out_paths.append(out_path)
    return out_paths
