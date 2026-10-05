"""Forecast-conditioned pricing (SPEC §7.7):

    observed_to_date + forecast quantiles for next h days + simulator for remainder
                   v (quantile-mapping of simulated near-term totals to forecast)
           forecast-conditioned payoff distribution (P) -> apply lambda -> Q price + band

The idea: the chain-dependent simulator (M5) is a good *generative*
model of day-to-day rainfall structure (wet/dry persistence, realistic
spell lengths, calibrated seasonal-total variance via the overdispersion
fix) but has no way to know "it's been drier than usual the last two
weeks" — it only knows calendar day-of-year and the covariates baked
into its GLM fit. A forecast (M7's ladder) *does* carry that
information, but only for a short horizon — extending any of M7's rungs
to the full remaining season would mean conditioning on information
that thins out fast. This module gets the best of both: trust the
forecast for the near term (the next `h` days), trust the simulator's
generative structure for the far term, and splice them together by
*quantile-mapping* the simulator's own near-term output onto the
forecast's marginal distribution — which keeps the simulator's full
day-by-day path structure (spell lengths, autocorrelation) while
correcting its marginal to match whatever the forecast actually says.

**Why plain climatology, not `enso_clim_v1`/`analog_v1`/an LightGBM
rung, for "forecast quantiles for next h days"**: M7's own real
walk-forward backtest (`docs/methods/forecasting.md`) found plain
climatology had the best CRPS of all 5 built rungs at n=31 seasons —
using it here is the data-driven choice this project's own evidence
supports, not an arbitrary default or an unexamined shortcut.

**No simulator change needed for the near-term/remainder split**: every
RNG draw in both simulator backends (M5) is a pure function of
`(seed, path_id, day_index)` — never of total `n_days` — so running
`simulate()` twice with the *same* seed and *same* `start_date`, once
for `n_days=h` and once for `n_days=h+remainder_days`, gives
path-for-path IDENTICAL first-`h`-day draws between the two calls.
Subtracting the short run's terminal deviation from the long run's
isolates exactly the remainder's contribution — no new simulator
plumbing, no per-day output needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from scipy import stats

from mq.forecasting.lgbm_quantile import extrapolated_quantile_grid
from mq.index.lpa import DailyLPA, daily_lpa_lookup
from mq.pricing.simulator_glm import ChainModel
from mq.pricing.simulator_ref import SimRequest
from mq.pricing.simulator_ref import simulate as simulate_numpy


def quantile_map(simulated: np.ndarray, forecast_quantiles: dict[float, float]) -> np.ndarray:
    """Remaps `simulated`'s marginal distribution onto `forecast_quantiles`
    via rank-based CDF matching: each simulated value's own empirical
    percentile (plotting position `rank/(n+1)` — the same convention
    `mq.mpr.wang` uses to avoid the 0/1 endpoint singularities) is looked
    up against the forecast's quantile function. Preserves `simulated`'s
    path-for-path *ordering* (and hence whatever autocorrelation
    structure produced it) while replacing its marginal with the
    forecast's."""
    n = len(simulated)
    ranks = stats.rankdata(simulated, method="average") / (n + 1)
    q_levels, q_values = extrapolated_quantile_grid(forecast_quantiles)
    return np.interp(ranks, q_levels, q_values)


@dataclass(frozen=True)
class ConditionedPayoff:
    as_of: date
    horizon_days: int
    n_paths: int
    payoff: np.ndarray  # forecast-conditioned final index, one value per path
    band_width_90: float  # P95 - P5, diagnostic for "plot band width vs time"


def forecast_conditioned_payoff_distribution(
    model: ChainModel,
    daily_lpa: DailyLPA,
    *,
    observed_to_date: float,
    start_date: date,
    period_end: date,
    start_state: int,
    covariates: list[float],
    overdispersion_sd: float,
    forecast_quantiles: dict[float, float],
    horizon_days: int,
    n_paths: int,
    seed: int,
) -> ConditionedPayoff:
    """`forecast_quantiles` must be quantiles of RAW remaining rainfall
    (mm) over [start_date, min(start_date + horizon_days - 1, period_end)]
    — the same target definition `mq.forecasting.climatology
    .remaining_rain_climatology_2station` produces, so its output can be
    passed straight through."""
    total_days = (period_end - start_date).days + 1
    if total_days <= 0:
        raise ValueError(f"start_date={start_date} is not before period_end={period_end}")
    h = min(horizon_days, total_days)

    near_term_req = SimRequest(
        n_paths=n_paths,
        start_date=start_date,
        n_days=h,
        seed=seed,
        observed_to_date=0.0,
        start_state=start_state,
        covariates=covariates,
        overdispersion_sd=overdispersion_sd,
    )
    near_term = simulate_numpy(model, daily_lpa, near_term_req)

    if h < total_days:
        full_req = SimRequest(
            n_paths=n_paths,
            start_date=start_date,
            n_days=total_days,
            seed=seed,  # SAME seed -> first h days' draws are identical to near_term's
            observed_to_date=0.0,
            start_state=start_state,
            covariates=covariates,
            overdispersion_sd=overdispersion_sd,
        )
        full = simulate_numpy(model, daily_lpa, full_req)
        remainder_deviation = full.terminal_index - near_term.terminal_index
    else:
        remainder_deviation = np.zeros(n_paths)

    corrected_near_term_rain = quantile_map(near_term.seasonal_total_mm, forecast_quantiles)
    lpa_by_day = daily_lpa_lookup(daily_lpa)
    window_dates = [start_date + timedelta(days=t) for t in range(h)]
    try:
        lpa_sum_over_h = sum(lpa_by_day[(d.month, d.day)] for d in window_dates)
    except KeyError as exc:
        raise ValueError(f"no LPA value for calendar day {exc.args[0]}") from exc
    corrected_near_term_deviation = corrected_near_term_rain - lpa_sum_over_h

    payoff = observed_to_date + corrected_near_term_deviation + remainder_deviation
    band_width_90 = float(np.quantile(payoff, 0.95) - np.quantile(payoff, 0.05))

    return ConditionedPayoff(
        as_of=start_date - timedelta(days=1),
        horizon_days=h,
        n_paths=n_paths,
        payoff=payoff,
        band_width_90=band_width_90,
    )
