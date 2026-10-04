"""Index-distribution pricing (SPEC §7.3, F09): fit candidate P-measure
distributions to the historical burn sample.

Each candidate exposes the same small interface (`FittedDistribution`) so
`mq.pricing.selection` can score them uniformly via CRPS (always, from
Monte-Carlo samples) and log-likelihood (where a density is actually
defined — not for the bootstrap candidate, which is a resampling scheme,
not a density model; see its docstring).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import polars as pl
from scipy import stats

N_MC_SAMPLES = 5000


@dataclass(frozen=True)
class FittedDistribution:
    kind: str
    params: dict[str, float]
    samples: (
        np.ndarray
    )  # Monte-Carlo draws from the fitted distribution — used for CRPS + quantiles
    logpdf: Callable[[float], float] | None  # None where no density is defined (bootstrap)


def fit_gamma(data: np.ndarray, *, rng: np.random.Generator) -> FittedDistribution:
    shape, loc, scale = stats.gamma.fit(data)
    dist = stats.gamma(shape, loc=loc, scale=scale)
    return FittedDistribution(
        kind="gamma",
        params={"shape": shape, "loc": loc, "scale": scale},
        samples=dist.rvs(size=N_MC_SAMPLES, random_state=rng),
        logpdf=lambda x: float(dist.logpdf(x)),
    )


def fit_lognormal(data: np.ndarray, *, rng: np.random.Generator) -> FittedDistribution:
    shape, loc, scale = stats.lognorm.fit(data)
    dist = stats.lognorm(shape, loc=loc, scale=scale)
    return FittedDistribution(
        kind="lognormal",
        params={"shape": shape, "loc": loc, "scale": scale},
        samples=dist.rvs(size=N_MC_SAMPLES, random_state=rng),
        logpdf=lambda x: float(dist.logpdf(x)),
    )


def fit_weibull(data: np.ndarray, *, rng: np.random.Generator) -> FittedDistribution:
    shape, loc, scale = stats.weibull_min.fit(data)
    dist = stats.weibull_min(shape, loc=loc, scale=scale)
    return FittedDistribution(
        kind="weibull",
        params={"shape": shape, "loc": loc, "scale": scale},
        samples=dist.rvs(size=N_MC_SAMPLES, random_state=rng),
        logpdf=lambda x: float(dist.logpdf(x)),
    )


def fit_kde(
    data: np.ndarray,
    *,
    rng: np.random.Generator,
    bw_method: Literal["scott", "silverman"] | float = "silverman",
) -> FittedDistribution:
    kde = stats.gaussian_kde(data, bw_method=bw_method)
    bw = float(kde.factor)
    return FittedDistribution(
        kind="kde",
        params={"bw_factor": bw},
        samples=kde.resample(N_MC_SAMPLES, seed=rng).ravel(),
        logpdf=lambda x: float(kde.logpdf(x)[0]),
    )


def fit_kde_cv_bandwidth(
    data: np.ndarray,
    *,
    rng: np.random.Generator,
    candidate_bandwidths: Sequence[float] = (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5),
) -> FittedDistribution:
    """Silverman gives one bandwidth; this picks the bandwidth (as a
    factor relative to Silverman's) that maximises leave-one-out
    log-likelihood over `candidate_bandwidths` — SPEC's "KDE (Silverman +
    CV bandwidth)" as two distinct candidates, this being the second."""
    # bw_method as a scalar sets the KDE's covariance factor *directly*
    # (verified: gaussian_kde(data, bw_method=0.5).factor == 0.5, not
    # 0.5 x the dataset's own Silverman value) — so each candidate below
    # is one fixed, literal bandwidth value tested identically across
    # every leave-one-out fold, which is what bandwidth CV means.
    silverman_bw = float(stats.gaussian_kde(data).factor)
    best_bw_factor = candidate_bandwidths[0]
    best_score = -np.inf
    for factor in candidate_bandwidths:
        bw = silverman_bw * factor
        loo_ll = 0.0
        for i in range(len(data)):
            held_out = data[i]
            rest = np.delete(data, i)
            kde_i = stats.gaussian_kde(rest, bw_method=bw)
            loo_ll += float(kde_i.logpdf(held_out)[0])
        if loo_ll > best_score:
            best_score = loo_ll
            best_bw_factor = factor
    final_bw = silverman_bw * best_bw_factor
    kde = stats.gaussian_kde(data, bw_method=final_bw)
    return FittedDistribution(
        kind="kde_cv",
        params={
            "bw_factor_vs_silverman": best_bw_factor,
            "silverman_bw": silverman_bw,
            "final_bw": final_bw,
        },
        samples=kde.resample(N_MC_SAMPLES, seed=rng).ravel(),
        logpdf=lambda x: float(kde.logpdf(x)[0]),
    )


def fit_bootstrap(data: np.ndarray, *, rng: np.random.Generator) -> FittedDistribution:
    """Non-parametric resampling of the historical sample itself. Not a
    density model — `logpdf` is None by design; CRPS (computed from
    samples, no density needed) is the only score this candidate gets in
    selection."""
    return FittedDistribution(
        kind="bootstrap",
        params={"n_obs": len(data)},
        samples=rng.choice(data, size=N_MC_SAMPLES, replace=True),
        logpdf=None,
    )


def season_oni(
    climate_idx_oni: pl.DataFrame, *, year: int, months: tuple[int, int, int] = (8, 9, 10)
) -> float | None:
    """Mean ONI over `months` (default ASO, coincident with the NE
    monsoon's Sep-Dec onset) for one calendar `year`, from the
    `climate_idx` Parquet dataset (index="oni"). None if no ONI
    observation falls in that window for that year."""
    window = climate_idx_oni.filter(
        (pl.col("date").dt.year() == year) & (pl.col("date").dt.month().is_in(list(months)))
    )
    if window.height == 0:
        return None
    return float(window["value"].mean())  # type: ignore[arg-type]


def oni_terciles(year_oni: dict[int, float]) -> dict[int, int]:
    """Classifies each year into an ONI tercile (0=low/La Nina-ish,
    1=mid/neutral, 2=high/El Nino-ish) relative to the other years in
    `year_oni` — a within-sample classification, matching the product
    note's framing of "years with the same ONI tercile", not an absolute
    meteorological threshold."""
    values = sorted(year_oni.values())
    n = len(values)
    low_cut = values[n // 3]
    high_cut = values[(2 * n) // 3]
    return {
        year: (0 if v <= low_cut else (2 if v >= high_cut else 1)) for year, v in year_oni.items()
    }


def fit_enso_conditioned_climatology(
    data: np.ndarray,
    years: list[int],
    *,
    target_year: int,
    year_terciles: dict[int, int],
    rng: np.random.Generator,
    min_group_size: int = 5,
) -> FittedDistribution:
    """Empirical climatology from years sharing `target_year`'s ONI
    tercile. Falls back to the full sample (all `years`) if the matching
    subset is smaller than `min_group_size` — too few points to say
    anything ENSO-specific, and SPEC's own "report honestly" posture
    means falling back rather than overfitting a 2-3-point subset."""
    target_tercile = year_terciles.get(target_year)
    if target_tercile is None:
        subset = data
        used_fallback = True
    else:
        mask = np.array([year_terciles.get(y) == target_tercile for y in years])
        subset = data[mask]
        used_fallback = len(subset) < min_group_size
        if used_fallback:
            subset = data
    return FittedDistribution(
        kind="enso_climatology",
        params={"n_in_group": float(len(subset)), "used_fallback": float(used_fallback)},
        samples=rng.choice(subset, size=N_MC_SAMPLES, replace=True),
        logpdf=None,  # empirical group climatology — same reasoning as bootstrap
    )
