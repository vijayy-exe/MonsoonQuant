"""Daily Long Period Average (LPA) — the IMD climatological normal that the
CDR index deviates from (SPEC §7.2, VERIFY V4).

Per the official NCDEX product notes (specs/sources/ncdex_product_note_*):
"the LPA for 1 September at IMD Nungambakkam is derived by averaging the
rainfall recorded on 1 September for each year from 1971...up to 2020."
This module computes that same per-calendar-day average, from the IMD
gridded rainfall at the nearest cell to a station — a *proxy* LPA, since
the real one is computed by IMD from the station's own gauge, not the
0.25° grid (see `mq.index.proxy` for the proxy/official distinction)."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from mq.io.grid import nearest_cell


@dataclass(frozen=True)
class DailyLPA:
    cell_lat: float
    cell_lon: float
    base_period_start_year: int
    base_period_end_year: int
    n_years_by_day: dict[tuple[int, int], int]  # (month, day) -> years actually averaged
    table: pl.DataFrame  # columns: month, day, lpa_mm


def daily_lpa_lookup(daily_lpa: DailyLPA) -> dict[tuple[int, int], float]:
    """`daily_lpa.table` as a plain (month, day) -> lpa_mm dict — the
    shape the simulator needs for a fast per-calendar-day lookup (both
    `mq.pricing.simulator_ref` and `mq.pricing.simulator` build the same
    lookup from the same table; factored out once here)."""
    return dict(
        zip(
            zip(daily_lpa.table["month"].to_list(), daily_lpa.table["day"].to_list(), strict=True),
            daily_lpa.table["lpa_mm"].to_list(),
            strict=True,
        )
    )


def compute_daily_lpa(
    rain_grid: pl.DataFrame,
    *,
    lat: float,
    lon: float,
    base_period_start_year: int,
    base_period_end_year: int,
) -> DailyLPA:
    """Climatological mean rainfall for each (month, day), at the nearest
    grid cell to (lat, lon), averaged over years in
    [base_period_start_year, base_period_end_year]. Feb 29 is excluded —
    the official LPA tables are defined over the 365 non-leap calendar
    days (SPEC's product-note example walks 1971..2020 by calendar date,
    which only exists in leap years for Feb 29)."""
    cell_lat, cell_lon = nearest_cell(rain_grid, lat=lat, lon=lon)
    cell_df = rain_grid.filter((pl.col("lat") == cell_lat) & (pl.col("lon") == cell_lon))

    base = cell_df.filter(
        (pl.col("date").dt.year() >= base_period_start_year)
        & (pl.col("date").dt.year() <= base_period_end_year)
    ).with_columns(pl.col("date").dt.month().alias("month"), pl.col("date").dt.day().alias("day"))
    base = base.filter(~((pl.col("month") == 2) & (pl.col("day") == 29)))

    agg = base.group_by(["month", "day"]).agg(
        pl.col("rain_mm").mean().alias("lpa_mm"), pl.col("rain_mm").count().alias("n_years")
    )
    n_years_by_day = {
        (row["month"], row["day"]): row["n_years"]
        for row in agg.select(["month", "day", "n_years"]).iter_rows(named=True)
    }
    table = agg.select(["month", "day", "lpa_mm"]).sort(["month", "day"])

    return DailyLPA(
        cell_lat=cell_lat,
        cell_lon=cell_lon,
        base_period_start_year=base_period_start_year,
        base_period_end_year=base_period_end_year,
        n_years_by_day=n_years_by_day,
        table=table,
    )


def season_lpa_total(
    lpa: DailyLPA, *, start_month: int, start_day: int, end_month: int, end_day: int
) -> float:
    """Sum of daily LPA over [start, end] (inclusive), assuming the window
    doesn't wrap the calendar year — true for both RAINCHNNAI (Sep 1-Dec
    31) and RAINMUMBAI (Jun 1-Sep 30)."""
    start_key, end_key = start_month * 100 + start_day, end_month * 100 + end_day
    if start_key > end_key:
        raise NotImplementedError("year-wrapping seasons are not supported")
    # month/day come back as int8 from polars' .dt accessors — 9*100+1 = 901
    # overflows int8 (max 127) and silently wraps, so cast to a wide int first.
    day_key = pl.col("month").cast(pl.Int32) * 100 + pl.col("day").cast(pl.Int32)
    window = lpa.table.filter((day_key >= start_key) & (day_key <= end_key))
    return float(window["lpa_mm"].sum())
