"""clim_v1 — empirical climatology of remaining-period rainfall (SPEC §7.6).

The first rung of the forecasting ladder: for an issue date `as_of`, take
every historical year's actual rainfall over the same (month, day) window
— from `as_of`'s month/day through the period's end month/day — at the
nearest available grid cell to a reference point, and report its sample
quantiles. No model fitting, no covariates: this is what SPEC §2 calls the
"climatology-only forecaster" that must go live in Week 1, before any
better model exists, so the ledger has a timestamped prediction on record
before the season resolves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl

MODEL_ID = "clim_v1"
MODEL_VERSION = "0.1.0"

QUANTILE_LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]


@dataclass(frozen=True)
class ClimatologyForecast:
    as_of: date
    period_end: date
    cell_lat: float
    cell_lon: float
    n_years: int
    quantiles: dict[str, float]
    sample_values: list[float]


def _nearest_cell(rain_grid: pl.DataFrame, *, lat: float, lon: float) -> tuple[float, float]:
    cell = (
        rain_grid.with_columns(
            ((pl.col("lat") - lat) ** 2 + (pl.col("lon") - lon) ** 2).alias("_dist2")
        )
        .sort("_dist2")
        .select("lat", "lon")
        .unique(maintain_order=True)
        .head(1)
    )
    if cell.height == 0:
        raise ValueError("rain_grid is empty — no cell to select")
    row = cell.row(0)
    return float(row[0]), float(row[1])


def remaining_rain_climatology(
    rain_grid: pl.DataFrame,
    *,
    lat: float,
    lon: float,
    as_of: date,
    period_end_month: int,
    period_end_day: int,
) -> ClimatologyForecast:
    """Empirical distribution of rain accumulated from `as_of`'s (month, day)
    through (period_end_month, period_end_day), one sample per historical
    year present in `rain_grid` at the nearest grid cell to (lat, lon).

    Each year's window is independent of `as_of`'s actual year: this asks
    "historically, how much rain fell between this calendar date and the
    period end" — the climatological question, not a forecast conditioned
    on anything observed this season (that's `enso_clim_v1` and later
    rungs of the ladder)."""
    cell_lat, cell_lon = _nearest_cell(rain_grid, lat=lat, lon=lon)
    df = rain_grid.filter((pl.col("lat") == cell_lat) & (pl.col("lon") == cell_lon))

    years = sorted(df["date"].dt.year().unique().to_list())
    samples: list[float] = []
    for year in years:
        end_year = year if period_end_month >= as_of.month else year + 1
        try:
            start = date(year, as_of.month, as_of.day)
            end = date(end_year, period_end_month, period_end_day)
        except ValueError:
            continue  # e.g. as_of.day == 29 (Feb) in a non-leap historical year
        window = df.filter((pl.col("date") >= start) & (pl.col("date") <= end))
        if window.height == 0:
            continue
        samples.append(float(window["rain_mm"].sum()))

    if not samples:
        raise ValueError("no historical years available to build a climatology")

    series = pl.Series(samples)
    quantiles: dict[str, float] = {}
    for q in QUANTILE_LEVELS:
        value = series.quantile(q, interpolation="linear")
        assert value is not None  # series is non-empty, checked above
        quantiles[str(q)] = float(value)

    period_end_year = as_of.year if period_end_month >= as_of.month else as_of.year + 1
    return ClimatologyForecast(
        as_of=as_of,
        period_end=date(period_end_year, period_end_month, period_end_day),
        cell_lat=cell_lat,
        cell_lon=cell_lon,
        n_years=len(samples),
        quantiles=quantiles,
        sample_values=samples,
    )
