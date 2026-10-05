"""Uncertainty quantification for a calibrated market-price-of-risk
parameter (SPEC §7.5): three distinct sources, reported separately
rather than collapsed into one number, because they answer different
questions —

(a) **Parametric bootstrap over P-model parameters**: "if the
    historical sample had come out slightly differently, how different
    would the calibrated λ/θ be?" Implemented by resampling the
    underlying years with replacement and recalibrating each time —
    the caller supplies `payoffs_from_years`, a function turning one
    resampled set of years into a payoff sample, so the same bootstrap
    loop serves both a burn sample (resampled years *are* the payoff
    sample) and a fitted-distribution candidate (resample years, refit
    the distribution, redraw its Monte Carlo sample).
(b) **Monte Carlo error**: "even with the P-model fixed and known,
    how much noise does a finite payoff sample add to the price
    estimate itself?" Closed-form via the delta method: the price's
    own standard error (from the weighted sample's effective size)
    propagated through the local slope dprice/dparam into an implied
    standard error on the calibrated parameter.
(c) **Bayesian pooled estimate across dates**: SPEC's headline number —
    combine several dates' calibrated λ (or θ) estimates, each with its
    own standard error and trading-volume weight, with a weak N(0,1)
    prior, via the standard conjugate normal-normal update (liquidity
    weighting = higher-volume dates get more precision in the
    likelihood). Generic and testable without any real market data —
    the real-data application (pooling actual NCDEX settlement dates)
    is blocked on the same bot-gated bhavcopy feed as M2, not on this
    function.

Language rule (SPEC §16): report these as "early empirical estimate",
never as a definitive statement of a risk premium.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats

PRIOR_MEAN = 0.0
PRIOR_SD = 1.0  # SPEC's weak N(0,1) prior


@dataclass(frozen=True)
class BootstrapResult:
    samples: np.ndarray  # one calibrated param per bootstrap replicate
    median: float
    lo90: float
    hi90: float
    n_bootstrap: int


def bootstrap_parameter_ci(
    years: Sequence[int],
    payoffs_from_years: Callable[[Sequence[int]], np.ndarray],
    calibrate_fn: Callable[[np.ndarray], float],
    *,
    n_bootstrap: int = 1000,
    seed: int = 0,
) -> BootstrapResult:
    """`calibrate_fn` takes a payoff sample and returns a single
    calibrated parameter (e.g. `lambda calibrate_wang(p, settle).param`)
    — kept generic so this works for both Wang and Esscher without
    duplicating the resampling loop."""
    rng = np.random.default_rng(seed)
    n_years = len(years)
    samples = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        resampled_years = [years[i] for i in rng.integers(0, n_years, size=n_years)]
        payoffs = payoffs_from_years(resampled_years)
        samples[b] = calibrate_fn(payoffs)
    return BootstrapResult(
        samples=samples,
        median=float(np.median(samples)),
        lo90=float(np.quantile(samples, 0.05)),
        hi90=float(np.quantile(samples, 0.95)),
        n_bootstrap=n_bootstrap,
    )


def mc_standard_error(
    payoffs: np.ndarray,
    weights: np.ndarray,
    price_fn: Callable[[float], float],
    param: float,
    *,
    bump: float = 1e-3,
) -> float:
    """Delta-method standard error of `param` from the price estimate's
    own Monte Carlo noise at fixed `param`: se_price (from the weighted
    sample's effective size) divided by the local slope |dprice/dparam|
    (central difference at `param +/- bump`). `weights` is whatever
    weighting scheme price_fn uses internally (Wang's order-statistic
    weights or Esscher's importance weights) — passed in rather than
    recomputed, since the caller already has it from calibration."""
    ess = 1.0 / np.sum(weights**2)
    weighted_mean = float(np.sum(weights * payoffs))
    weighted_var = float(np.sum(weights * (payoffs - weighted_mean) ** 2))
    se_price = float(np.sqrt(weighted_var / ess))

    slope = (price_fn(param + bump) - price_fn(param - bump)) / (2 * bump)
    if slope == 0:
        return float("inf")
    return se_price / abs(slope)


@dataclass(frozen=True)
class PooledEstimate:
    posterior_mean: float
    posterior_sd: float
    lo90: float
    hi90: float
    n_obs: int
    total_volume: float


def bayesian_pool(
    param_estimates: Sequence[float],
    standard_errors: Sequence[float],
    volumes: Sequence[float],
    *,
    prior_mean: float = PRIOR_MEAN,
    prior_sd: float = PRIOR_SD,
) -> PooledEstimate:
    """Conjugate normal-normal pooling of per-date calibrated
    parameters. Each date's likelihood precision is its own
    1/standard_error^2, scaled by its (normalized) trading-volume share
    — a zero-volume date contributes nothing, matching "liquidity-
    weighted likelihood" in SPEC §7.5 literally rather than treating
    every date as equally informative regardless of how thin its
    market was that day."""
    if not (len(param_estimates) == len(standard_errors) == len(volumes)):
        raise ValueError("param_estimates, standard_errors, and volumes must be the same length")
    n = len(param_estimates)
    total_volume = float(np.sum(volumes))
    if total_volume <= 0:
        raise ValueError("total_volume must be positive to form liquidity weights")
    volume_weights = np.asarray(volumes, dtype=float) / total_volume

    prior_precision = 1.0 / prior_sd**2
    data_precisions = volume_weights * n / np.asarray(standard_errors, dtype=float) ** 2
    # volume_weights sum to 1, so "* n" keeps the *average* date's
    # contribution on the same precision scale as its own 1/se^2 would
    # be alone -- a liquidity weight of 1/n (average volume) reproduces
    # the unweighted pooled-precision formula exactly.
    posterior_precision = prior_precision + float(np.sum(data_precisions))
    posterior_mean = (
        prior_precision * prior_mean + float(np.sum(data_precisions * np.asarray(param_estimates)))
    ) / posterior_precision
    posterior_sd = float(np.sqrt(1.0 / posterior_precision))

    lo90 = float(stats.norm.ppf(0.05, loc=posterior_mean, scale=posterior_sd))
    hi90 = float(stats.norm.ppf(0.95, loc=posterior_mean, scale=posterior_sd))
    return PooledEstimate(
        posterior_mean=posterior_mean,
        posterior_sd=posterior_sd,
        lo90=lo90,
        hi90=hi90,
        n_obs=n,
        total_volume=total_volume,
    )
