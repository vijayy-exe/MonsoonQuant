"""clim_v1 and enso_clim_v1 — the first two rungs of the forecasting
ladder (SPEC §7.6).

`clim_v1`: for an issue date `as_of`, take every historical year's
actual rainfall over the same (month, day) window — from `as_of`'s
month/day through the period's end month/day — at the nearest available
grid cell to a reference point, and report its sample quantiles. No
model fitting, no covariates: this is what SPEC §2 calls the
"climatology-only forecaster" that must go live in Week 1, before any
better model exists, so the ledger has a timestamped prediction on record
before the season resolves.

`enso_clim_v1`: the same empirical-quantile idea, but conditioned on
ONI tercile — "years with the same ONI tercile as this one" rather than
every year equally. Built on `mq.forecasting.features.build_training_rows`'s
training table (2-station averaged series) rather than clim_v1's
single-station lookup, and reuses `mq.pricing.distribution.oni_terciles`
— the same within-sample tercile classification M4's
`fit_enso_conditioned_climatology` already uses for burn-sample pricing,
applied here to remaining-period rainfall at a specific issue date
instead of a season's final payoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import polars as pl

from mq.io.grid import nearest_cell
from mq.pricing.distribution import oni_terciles

MODEL_ID = "clim_v1"
MODEL_VERSION = "0.1.0"

ENSO_MODEL_ID = "enso_clim_v1"
ENSO_MODEL_VERSION = "0.1.0"

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
    cell_lat, cell_lon = nearest_cell(rain_grid, lat=lat, lon=lon)
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


@dataclass(frozen=True)
class HorizonClimatologyForecast:
    as_of: date
    window_end: date
    n_years: int
    quantiles: dict[str, float]
    sample_values: list[float]


def remaining_rain_climatology_2station(
    avg_series: pl.DataFrame,
    *,
    as_of: date,
    period_end_month: int,
    period_end_day: int,
    max_horizon_days: int | None = None,
) -> HorizonClimatologyForecast:
    """Like `remaining_rain_climatology`, but on an already 2-station-
    averaged `avg_series` (see `mq.forecasting.features.station_average_daily_series`
    — M8's forecast-conditioned pricing needs the forecast and the
    simulator on the same station basis), and with an optional
    `max_horizon_days` cap: when given, each year's window ends at
    `min(real period_end, as_of + max_horizon_days)` instead of running
    all the way to period_end — M8's "forecast quantiles for the next h
    days" (SPEC §7.7), as opposed to M7's full-remaining-season target.

    Climatology (plain, unconditioned) rather than `enso_clim_v1`/
    `analog_v1`/an LightGBM rung: M7's own real backtest
    (docs/methods/forecasting.md) found plain climatology had the best
    CRPS of all 5 built rungs at this sample size — using it here is the
    data-driven choice, not an arbitrary default."""
    years = sorted(avg_series["date"].dt.year().unique().to_list())
    samples: list[float] = []
    for year in years:
        end_year = year if period_end_month >= as_of.month else year + 1
        try:
            start = date(year, as_of.month, as_of.day)
            real_end = date(end_year, period_end_month, period_end_day)
        except ValueError:
            continue  # e.g. as_of.day == 29 (Feb) in a non-leap historical year
        end = (
            real_end
            if max_horizon_days is None
            else min(real_end, start + timedelta(days=max_horizon_days))
        )
        window = avg_series.filter((pl.col("date") >= start) & (pl.col("date") <= end))
        if window.height == 0:
            continue
        samples.append(float(window["rain_mm"].sum()))

    if not samples:
        raise ValueError("no historical years available to build a climatology")

    series = pl.Series(samples)
    quantiles: dict[str, float] = {}
    for q in QUANTILE_LEVELS:
        value = series.quantile(q, interpolation="linear")
        assert value is not None
        quantiles[str(q)] = float(value)

    period_end_year = as_of.year if period_end_month >= as_of.month else as_of.year + 1
    real_period_end = date(period_end_year, period_end_month, period_end_day)
    window_end = (
        real_period_end
        if max_horizon_days is None
        else min(real_period_end, as_of + timedelta(days=max_horizon_days))
    )
    return HorizonClimatologyForecast(
        as_of=as_of,
        window_end=window_end,
        n_years=len(samples),
        quantiles=quantiles,
        sample_values=samples,
    )


@dataclass(frozen=True)
class EnsoClimatologyForecast:
    target_year: int
    issue_date: date
    target_oni: float
    target_tercile: int
    n_in_group: int
    used_fallback: bool
    quantiles: dict[str, float]
    sample_values: list[float]


def _quantiles_from_samples(samples: np.ndarray) -> dict[str, float]:
    series = pl.Series(samples)
    quantiles: dict[str, float] = {}
    for q in QUANTILE_LEVELS:
        value = series.quantile(q, interpolation="linear")
        assert value is not None
        quantiles[str(q)] = float(value)
    return quantiles


def enso_conditioned_remaining_rain_forecast(
    training_rows: pl.DataFrame,
    *,
    target_year: int,
    issue_date: date,
    min_group_size: int = 5,
) -> EnsoClimatologyForecast:
    """Empirical quantiles of `target_remaining_rain_mm` from years
    sharing `target_year`'s ONI tercile, at the SAME calendar issue-day
    across years (`training_rows` from
    `mq.forecasting.features.build_training_rows`). `target_year`'s own
    row is excluded from the sample pool — this forecasts year
    `target_year` using *other* years' analogs, the structure a
    walk-forward backtest needs to stay honest. Falls back to the full
    cross-year sample (still excluding `target_year`) if the matching
    tercile group is smaller than `min_group_size` — same posture as
    M4's `fit_enso_conditioned_climatology`."""
    same_day = training_rows.filter(
        (pl.col("issue_month") == issue_date.month) & (pl.col("issue_day") == issue_date.day)
    )
    target_row = same_day.filter(pl.col("year") == target_year)
    if target_row.height == 0:
        raise ValueError(f"no training row for target_year={target_year} issue_date={issue_date}")
    target_oni = float(target_row["oni"][0])

    other = same_day.filter(pl.col("year") != target_year)
    year_oni = dict(zip(other["year"].to_list(), other["oni"].to_list(), strict=True))
    year_oni[target_year] = target_oni
    terciles = oni_terciles(year_oni)
    target_tercile = terciles[target_year]

    matching_years = [y for y, t in terciles.items() if t == target_tercile and y != target_year]
    used_fallback = len(matching_years) < min_group_size
    if used_fallback:
        matching_years = [y for y in terciles if y != target_year]

    pool = other.filter(pl.col("year").is_in(matching_years))
    samples = pool["target_remaining_rain_mm"].to_numpy()
    if len(samples) == 0:
        raise ValueError(
            f"no analog years available for target_year={target_year} issue_date={issue_date}"
        )

    return EnsoClimatologyForecast(
        target_year=target_year,
        issue_date=issue_date,
        target_oni=target_oni,
        target_tercile=target_tercile,
        n_in_group=len(samples),
        used_fallback=used_fallback,
        quantiles=_quantiles_from_samples(samples),
        sample_values=samples.tolist(),
    )
