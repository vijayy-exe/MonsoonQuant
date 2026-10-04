"""Distribution selection via rolling-origin CV (SPEC §7.3, §9): score
every candidate distribution on held-out years via CRPS and (where a
density is defined) log-likelihood, and pick the lowest-CRPS candidate.
AIC is explicitly not used as the primary criterion here, per SPEC.

With n=31 (RAINCHNNAI's full real backfill), "rolling-origin" is
implemented as leave-one-out — the maximal use of data at this sample
size; a true walk-forward split would leave too few points per fold to
fit a 3-parameter distribution at all.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
import scoringrules as sr

from mq.pricing.distribution import (
    FittedDistribution,
    fit_bootstrap,
    fit_enso_conditioned_climatology,
    fit_gamma,
    fit_kde,
    fit_kde_cv_bandwidth,
    fit_lognormal,
    fit_weibull,
    oni_terciles,
    season_oni,
)

PARAMETRIC_FITTERS = {
    "gamma": fit_gamma,
    "lognormal": fit_lognormal,
    "weibull": fit_weibull,
    "kde_silverman": fit_kde,
    "kde_cv": fit_kde_cv_bandwidth,
    "bootstrap": fit_bootstrap,
}


@dataclass(frozen=True)
class CVResult:
    kind: str
    n_folds: int
    mean_crps: float
    mean_log_likelihood: float | None  # None if no fold had a defined density


def _crps_for_fold(held_out: float, fd: FittedDistribution) -> float:
    return float(sr.crps_ensemble(held_out, fd.samples))


def rolling_origin_cv(
    payoffs: np.ndarray,
    years: list[int],
    *,
    oni: pl.DataFrame | None = None,
    rng: np.random.Generator,
) -> dict[str, CVResult]:
    """Leave-one-out CV of every candidate in PARAMETRIC_FITTERS, plus
    ENSO-conditioned climatology if `oni` (the real climate_idx ONI
    Parquet data) is supplied."""
    n = len(payoffs)
    crps_by_kind: dict[str, list[float]] = {k: [] for k in PARAMETRIC_FITTERS}
    ll_by_kind: dict[str, list[float]] = {k: [] for k in PARAMETRIC_FITTERS}

    year_terciles = None
    if oni is not None:
        year_oni = {y: season_oni(oni, year=y) for y in years}
        known = {y: v for y, v in year_oni.items() if v is not None}
        year_terciles = oni_terciles(known)
        crps_by_kind["enso_climatology"] = []
        ll_by_kind["enso_climatology"] = []

    for i in range(n):
        held_out = payoffs[i]
        train = np.delete(payoffs, i)
        train_years = years[:i] + years[i + 1 :]

        for kind, fitter in PARAMETRIC_FITTERS.items():
            fd = fitter(train, rng=rng)
            crps_by_kind[kind].append(_crps_for_fold(held_out, fd))
            if fd.logpdf is not None:
                ll_by_kind[kind].append(fd.logpdf(held_out))

        if year_terciles is not None:
            fd = fit_enso_conditioned_climatology(
                train, train_years, target_year=years[i], year_terciles=year_terciles, rng=rng
            )
            crps_by_kind["enso_climatology"].append(_crps_for_fold(held_out, fd))

    results = {}
    for kind, crps_list in crps_by_kind.items():
        ll_list = ll_by_kind.get(kind, [])
        results[kind] = CVResult(
            kind=kind,
            n_folds=len(crps_list),
            mean_crps=float(np.mean(crps_list)),
            mean_log_likelihood=float(np.mean(ll_list)) if ll_list else None,
        )
    return results


def select_best_distribution(cv_results: dict[str, CVResult]) -> str:
    """Lowest mean CRPS wins — SPEC's primary selection criterion.
    Log-likelihood is diagnostic (see docs/methods/burn_distribution.md),
    not used to break ties here, since CRPS already orders every
    candidate including the two (bootstrap, enso_climatology) with no
    defined density."""
    return min(cv_results, key=lambda k: cv_results[k].mean_crps)


def log_cv_results_to_mlflow(
    cv_results: dict[str, CVResult],
    *,
    contract_code: str,
    tracking_uri: str,
    experiment_name: str = "burn_distribution_selection",
) -> str:
    """Logs each candidate's CV scores as one MLflow run, plus a parent
    summary run naming the winner. Returns the winning candidate's kind.
    Import is local to keep mlflow off the hot import path for code that
    never touches distribution selection."""
    import mlflow

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)

    best = select_best_distribution(cv_results)
    with mlflow.start_run(run_name=f"{contract_code}_selection"):
        mlflow.log_param("contract_code", contract_code)
        mlflow.log_param("selected_kind", best)
        mlflow.log_param("n_candidates", len(cv_results))
        for kind, r in cv_results.items():
            with mlflow.start_run(run_name=f"{contract_code}_{kind}", nested=True):
                mlflow.log_param("kind", kind)
                mlflow.log_param("n_folds", r.n_folds)
                mlflow.log_metric("mean_crps", r.mean_crps)
                if r.mean_log_likelihood is not None:
                    mlflow.log_metric("mean_log_likelihood", r.mean_log_likelihood)
    return best
