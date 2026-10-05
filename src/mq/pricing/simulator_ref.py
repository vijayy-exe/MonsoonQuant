"""NumPy reference implementation of the chain-dependent rainfall
simulator (SPEC §7.4, F10, M5.2).

Simulates day-by-day from a fitted `ChainModel` (M5.1): draw a wet/dry
state from the 2-state Markov occurrence chain, and — on a wet day — a
rainfall amount from the Gamma amount model. Each day's simulated CDR
*deviation* (rain - LPA) accumulates into the terminal index value,
exactly mirroring `mq.index.engine.compute_index`'s own
anchor-plus-cumulative-deviation definition.

**Scope of this module**: single representative daily series (one
station, or an already-averaged multi-station series built the same way
`mq.index.engine` averages its stations) — correlated multi-station
simulation is SPEC's own P2 "Wilks" deferral (F24), not attempted here.

**Overdispersion fix** (SPEC §7.4's "under-disperse seasonal totals"
problem): a chain-dependent model driven only by its fitted daily GLMs
reliably *under*-disperses the sum of many days, because it has no
path-to-path parameter uncertainty — every path drifts toward the same
mean. The fix SPEC calls for is a season-level random effect drawn once
per path. Implemented here as one lognormal multiplier (mean 1, free sd)
applied to that path's entire wet-day amount-mean for every day of the
season — a single number per path, not per day, which is what makes
whole seasons correlate instead of just adding daily noise.
`calibrate_overdispersion_sd` finds the multiplier's sd that reproduces
a target seasonal-total standard deviation (typically the real
historical burn sample's sd), via a 1-D root-find — this is the
mechanism that satisfies SPEC's "seasonal-total sd within ±10%"
acceptance bullet.

Day-of-year handling: `start_date` + the local days-since-start index is
converted to real calendar dates, so Fourier phase and the LPA
(month, day) lookup both use genuine calendar dates — this only needs
within-one-contract-season date arithmetic (never wraps past Dec 31
into a new year), since neither RAINCHNNAI (Sep 1-Dec 31) nor RAINMUMBAI
(Jun 1-Sep 30) crosses a year boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from scipy import optimize

from mq.index.lpa import DailyLPA
from mq.pricing.simulator_glm import (
    ChainModel,
    fourier_design,
    predict_gamma_mean,
    predict_logistic,
)


@dataclass(frozen=True)
class SimRequest:
    n_paths: int
    start_date: date  # first day to simulate
    n_days: int
    seed: int
    observed_to_date: float  # CDR spot value already accumulated before start_date
    start_state: int  # wet(1)/dry(0) state of the day *before* start_date
    covariates: list[float]  # one value per model.covariate_cols, held constant over the horizon
    overdispersion_sd: float = 0.0  # season-level lognormal-multiplier sd; 0.0 = fix disabled


@dataclass(frozen=True)
class SimResult:
    terminal_index: np.ndarray  # shape (n_paths,): observed_to_date + cumulative deviation
    seasonal_total_mm: np.ndarray  # shape (n_paths,): simulated rain total only (diagnostic)


def _lpa_lookup(daily_lpa: DailyLPA) -> dict[tuple[int, int], float]:
    return dict(
        zip(
            zip(daily_lpa.table["month"].to_list(), daily_lpa.table["day"].to_list(), strict=True),
            daily_lpa.table["lpa_mm"].to_list(),
            strict=True,
        )
    )


def simulate(model: ChainModel, daily_lpa: DailyLPA, request: SimRequest) -> SimResult:
    if len(request.covariates) != len(model.covariate_cols):
        raise ValueError(
            f"request supplies {len(request.covariates)} covariate value(s), "
            f"model expects {len(model.covariate_cols)} ({model.covariate_cols})"
        )
    rng = np.random.default_rng(request.seed)
    n, d = request.n_paths, request.n_days

    dates = [request.start_date + timedelta(days=t) for t in range(d)]
    doy = np.array([dt.timetuple().tm_yday for dt in dates], dtype=float)
    lpa_by_day = _lpa_lookup(daily_lpa)
    try:
        lpa_mm = np.array([lpa_by_day[(dt.month, dt.day)] for dt in dates])
    except KeyError as exc:
        raise ValueError(f"no LPA value for calendar day {exc.args[0]}") from exc

    cov = (
        np.tile(np.asarray(request.covariates, dtype=float), (d, 1))
        if request.covariates
        else np.zeros((d, 0))
    )
    design = np.concatenate([fourier_design(doy, n_harmonics=model.n_harmonics), cov], axis=1)
    p01 = predict_logistic(model.occurrence_01, design)
    p11 = predict_logistic(model.occurrence_11, design)
    mean_amt = predict_gamma_mean(model.amount, design)
    shape = model.amount.extra["shape"]

    if request.overdispersion_sd > 0:
        sigma = request.overdispersion_sd
        season_effect = rng.lognormal(mean=-0.5 * sigma**2, sigma=sigma, size=n)
    else:
        season_effect = np.ones(n)

    state = np.full(n, request.start_state, dtype=np.int64)
    cumulative_deviation = np.zeros(n)
    seasonal_total = np.zeros(n)
    for t in range(d):
        p_wet = np.where(state == 1, p11[t], p01[t])
        wet = rng.random(n) < p_wet
        amt = np.zeros(n)
        n_wet = int(wet.sum())
        if n_wet > 0:
            scale = (mean_amt[t] * season_effect[wet]) / shape
            amt[wet] = rng.gamma(shape, scale, size=n_wet)
        cumulative_deviation += amt - lpa_mm[t]
        seasonal_total += amt
        state = wet.astype(np.int64)

    return SimResult(
        terminal_index=request.observed_to_date + cumulative_deviation,
        seasonal_total_mm=seasonal_total,
    )


def calibrate_overdispersion_sd(
    model: ChainModel,
    daily_lpa: DailyLPA,
    request_template: SimRequest,
    *,
    target_seasonal_total_sd: float,
    calibration_n_paths: int = 4000,
    bracket: tuple[float, float] = (1e-6, 2.0),
) -> float:
    """Finds the lognormal-multiplier sd whose simulated
    `seasonal_total_mm` standard deviation matches
    `target_seasonal_total_sd` — the mechanism behind SPEC's
    "seasonal-total sd within ±10%" validation requirement. A 1-D
    root-find (Brent) over `bracket`: `simulate`'s seasonal-total sd is
    monotonically increasing in the multiplier's sd (more path-to-path
    amount-mean spread can only add variance, never remove it), so a
    bracketing root-finder is the right tool, not an iterative search."""

    def _gap(sigma: float) -> float:
        req = SimRequest(
            n_paths=calibration_n_paths,
            start_date=request_template.start_date,
            n_days=request_template.n_days,
            seed=request_template.seed,
            observed_to_date=request_template.observed_to_date,
            start_state=request_template.start_state,
            covariates=request_template.covariates,
            overdispersion_sd=sigma,
        )
        result = simulate(model, daily_lpa, req)
        return float(np.std(result.seasonal_total_mm, ddof=1)) - target_seasonal_total_sd

    lo, hi = bracket
    if _gap(lo) > 0:
        return lo  # even the floor already overshoots — no fix needed, report the minimum
    if _gap(hi) < 0:
        raise ValueError(
            f"target_seasonal_total_sd={target_seasonal_total_sd} unreachable within "
            f"bracket={bracket} — widen the upper bound"
        )
    return float(optimize.brentq(_gap, lo, hi, xtol=1e-3))
