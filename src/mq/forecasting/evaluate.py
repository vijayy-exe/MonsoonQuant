"""Forecasting-ladder metrics and walk-forward CV harness (SPEC §7.6).

Every rung in the ladder (the climatology baseline recomputed here for
fair comparison, `enso_clim_v1`, `analog_v1`, and later the LightGBM
rungs) reports an empirical sample for a given (target_year, issue_date)
— one metric suite serves all of them uniformly, the same CRPS-first
posture M4's distribution selection already established (`crps_ensemble`
from `scoringrules`, already a dependency).

**Walk-forward only**: "train <= year y-1, test y" (SPEC §7.6). The
harness builds, for each test year, a tiny table combining the
strictly-prior years with the single target row being forecast, then
calls the model function on that — the same input shape
`enso_conditioned_remaining_rain_forecast`/`analog_forecast` already
expect (a table containing the target row plus the years to compare it
against), so no separate code path is needed for backtesting versus a
live forecast.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl
import scoringrules as sr

QUANTILE_LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
COVERAGE_LEVELS = [0.5, 0.9]

ModelFn = Callable[[pl.DataFrame, int, date], np.ndarray]


def crps(samples: np.ndarray, actual: float) -> float:
    return float(sr.crps_ensemble(actual, samples))


def crpss(model_mean_crps: float, reference_mean_crps: float) -> float:
    """CRPS skill score vs a reference model's mean CRPS over the SAME
    walk-forward split: >0 means the model beats the reference (SPEC's
    own acceptance bullet). Not computed per-row -- aggregate mean CRPS
    on both sides, the standard CRPSS definition."""
    if reference_mean_crps == 0:
        return float("nan")
    return 1.0 - model_mean_crps / reference_mean_crps


def pinball_loss(samples: np.ndarray, actual: float, q: float) -> float:
    forecast_q = float(np.quantile(samples, q))
    diff = actual - forecast_q
    return float(max(q * diff, (q - 1) * diff))


def interval_coverage_hit(samples: np.ndarray, actual: float, level: float) -> bool:
    """True if `actual` falls inside the central `level`-fraction
    interval of `samples` (e.g. level=0.9 -> [P5, P95])."""
    lo = float(np.quantile(samples, (1 - level) / 2))
    hi = float(np.quantile(samples, (1 + level) / 2))
    return bool(lo <= actual <= hi)


def pit_value(samples: np.ndarray, actual: float) -> float:
    """Probability integral transform: the empirical CDF of `samples`
    evaluated at `actual`. A well-calibrated forecaster's PIT values,
    pooled across many (samples, actual) pairs, are approximately
    Uniform(0,1) -- bin them yourself (e.g. `np.histogram`) for a PIT
    histogram; this function returns one value per pair, not a plot."""
    return float(np.mean(samples <= actual))


def reliability_curve(
    pairs: list[tuple[np.ndarray, float]], levels: list[float] = QUANTILE_LEVELS
) -> dict[float, float]:
    """For each nominal quantile level q, the empirical fraction of
    `actual`s that fell at or below that pair's forecast q-quantile.
    Perfect calibration: result[q] == q. This is the reliability
    diagram's underlying data, not the plot itself."""
    result: dict[float, float] = {}
    for q in levels:
        hits = [actual <= np.quantile(samples, q) for samples, actual in pairs]
        result[q] = float(np.mean(hits))
    return result


@dataclass(frozen=True)
class BacktestResult:
    model_id: str
    n_predictions: int
    mean_crps: float
    mean_pinball_by_q: dict[float, float]
    coverage_by_level: dict[float, float]
    pit_values: list[float]


def climatology_baseline_forecast(
    training_rows: pl.DataFrame, target_year: int, issue_date: date
) -> np.ndarray:
    """The climatology recomputed consistently with the ladder's other
    rungs (2-station averaged series — see `mq.forecasting.features`'s
    module docstring on why this isn't literally `clim_v1`'s own
    single-station function): every other year's `target_remaining_rain_mm`
    at the same calendar issue-day, unconditioned on anything."""
    same_day = training_rows.filter(
        (pl.col("issue_month") == issue_date.month) & (pl.col("issue_day") == issue_date.day)
    )
    other = same_day.filter(pl.col("year") != target_year)
    if other.height == 0:
        raise ValueError(f"no climatology analog years for issue_date={issue_date}")
    return other["target_remaining_rain_mm"].to_numpy()


def walk_forward_backtest(
    training_rows: pl.DataFrame,
    model_fn: ModelFn,
    *,
    model_id: str,
    min_train_years: int = 5,
) -> BacktestResult:
    """Iterates test years in ascending order; a test year is included
    only once at least `min_train_years` strictly-earlier years are
    available (SPEC's "train <= year y-1"). A row the model can't
    forecast (raises ValueError, e.g. too few analog years) is skipped
    -- not fabricated -- and doesn't count toward `n_predictions`."""
    years = sorted(training_rows["year"].unique().to_list())

    crps_values: list[float] = []
    pinball_by_q: dict[float, list[float]] = {q: [] for q in QUANTILE_LEVELS}
    coverage_hits: dict[float, list[bool]] = {level: [] for level in COVERAGE_LEVELS}
    pit_values: list[float] = []

    for i, test_year in enumerate(years):
        prior_years = years[:i]
        if len(prior_years) < min_train_years:
            continue
        train_subset = training_rows.filter(pl.col("year").is_in(prior_years))
        test_rows = training_rows.filter(pl.col("year") == test_year)

        for row in test_rows.iter_rows(named=True):
            issue_date = row["issue_date"]
            actual = row["target_remaining_rain_mm"]
            single_row = test_rows.filter(pl.col("issue_date") == issue_date)
            call_table = pl.concat([train_subset, single_row])
            try:
                samples = model_fn(call_table, test_year, issue_date)
            except ValueError:
                continue

            crps_values.append(crps(samples, actual))
            for q in QUANTILE_LEVELS:
                pinball_by_q[q].append(pinball_loss(samples, actual, q))
            for level in COVERAGE_LEVELS:
                coverage_hits[level].append(interval_coverage_hit(samples, actual, level))
            pit_values.append(pit_value(samples, actual))

    if not crps_values:
        raise ValueError(
            f"no predictions produced for model_id={model_id} -- check min_train_years and "
            "training_rows coverage"
        )

    return BacktestResult(
        model_id=model_id,
        n_predictions=len(crps_values),
        mean_crps=float(np.mean(crps_values)),
        mean_pinball_by_q={q: float(np.mean(v)) for q, v in pinball_by_q.items()},
        coverage_by_level={level: float(np.mean(v)) for level, v in coverage_hits.items()},
        pit_values=pit_values,
    )
