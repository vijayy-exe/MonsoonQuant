"""Historical burn analysis (SPEC §7.3, F08): reconstruct the contract's
final-season CDR value for every historical year with full data coverage,
then summarize that sample as the first (crudest) fair-value benchmark.

For this CDR contract the index *is* the settlement price (Final
Settlement Price = the spot value on expiry day) — no separate payoff
transform at this stage. "Burn" here means: what would the index have
settled at, every year we can reconstruct it, using the real CDR
methodology (`mq.index.engine.compute_index`) rather than an approximation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import polars as pl
from scipy import stats

from mq.index.engine import compute_index
from mq.index.lpa import DailyLPA
from mq.specs.contract import ContractSpec, MonthDay

DetrendMethod = Literal["none", "linear", "loess"]


@dataclass(frozen=True)
class BurnSample:
    contract_code: str
    years: list[int]
    payoffs: list[float]  # one final CDR spot value per fully-reconstructable year


@dataclass(frozen=True)
class BurnStats:
    n: int
    mean: float
    median: float
    sd: float
    p5: float
    p25: float
    p75: float
    p95: float
    skew: float
    es_lower_5pct: float  # mean of the worst (lowest) 5% of outcomes
    es_upper_5pct: float  # mean of the best (highest) 5% of outcomes


def reconstruct_season(
    spec: ContractSpec,
    rain_grid: pl.DataFrame,
    year: int,
    *,
    lpa_cache: dict[tuple[str, int, int], DailyLPA] | None = None,
) -> float | None:
    """The final CDR spot value for one historical year's complete season,
    or None if `rain_grid` doesn't fully cover that year's window (reaches
    all the way to period_end) — skipped rather than extrapolated.

    Not a look-ahead violation to pass the full multi-year `rain_grid`
    here even for an early `year`: the LPA base period (e.g. 1971-2020)
    is a *fixed, pre-published* IMD reference table used identically for
    every contract year, not something recomputed per observation — using
    it for a 1995 reconstruction mirrors how the real contract actually
    works, where every participant sees the same static LPA regardless of
    which year they're looking at.

    `lpa_cache`: forwarded to `compute_index` — see its docstring. Lets a
    caller reconstructing many years (`build_burn_sample`) share one
    station-LPA computation across all of them instead of recomputing it
    per year."""
    if not isinstance(spec.index.period_end, MonthDay):
        raise TypeError("expected a resolved period_end")
    full_season_as_of = date(year, spec.index.period_end.month, spec.index.period_end.day)
    try:
        path = compute_index(spec, rain_grid, as_of=full_season_as_of, lpa_cache=lpa_cache)
    except ValueError:
        return None  # a data gap anywhere in the season — skip, don't guess
    if not path.dates or path.dates[-1] != full_season_as_of:
        return None
    return path.observed_to_date


def build_burn_sample(spec: ContractSpec, rain_grid: pl.DataFrame, years: list[int]) -> BurnSample:
    """Reconstruct every year in `years` independently; years without full
    season coverage are silently dropped (not every historical year will
    have complete data — SPEC's own §8.1 backfill expects gaps).

    All years share one `lpa_cache`: every call uses the same contract
    spec, so the same fixed LPA base period applies to every year — the
    per-station LPA groupby runs once total instead of once per year."""
    lpa_cache: dict[tuple[str, int, int], DailyLPA] = {}
    payoffs: list[float] = []
    used_years: list[int] = []
    for year in years:
        value = reconstruct_season(spec, rain_grid, year, lpa_cache=lpa_cache)
        if value is not None:
            payoffs.append(value)
            used_years.append(year)
    return BurnSample(contract_code=spec.contract_code, years=used_years, payoffs=payoffs)


def compute_burn_stats(sample: BurnSample) -> BurnStats:
    if len(sample.payoffs) < 2:
        raise ValueError(
            f"need at least 2 historical seasons to compute burn stats, got {len(sample.payoffs)}"
        )
    s = pl.Series(sample.payoffs).sort()
    n = s.len()
    tail_n = max(1, round(n * 0.05))

    return BurnStats(
        n=n,
        mean=float(s.mean()),  # type: ignore[arg-type]
        median=float(s.median()),  # type: ignore[arg-type]
        sd=float(s.std()),  # type: ignore[arg-type]
        p5=float(s.quantile(0.05, interpolation="linear")),  # type: ignore[arg-type]
        p25=float(s.quantile(0.25, interpolation="linear")),  # type: ignore[arg-type]
        p75=float(s.quantile(0.75, interpolation="linear")),  # type: ignore[arg-type]
        p95=float(s.quantile(0.95, interpolation="linear")),  # type: ignore[arg-type]
        skew=float(s.skew()) if n >= 3 else float("nan"),  # type: ignore[arg-type]
        es_lower_5pct=float(s.head(tail_n).mean()),  # type: ignore[arg-type]
        es_upper_5pct=float(s.tail(tail_n).mean()),  # type: ignore[arg-type]
    )


@dataclass(frozen=True)
class DetrendedSample:
    contract_code: str
    method: DetrendMethod
    years: list[int]
    payoffs: list[float]  # detrended and re-centered -- see detrend_sample's docstring


def _linear_trend(years: np.ndarray, payoffs: np.ndarray) -> np.ndarray:
    fit = stats.linregress(years, payoffs)
    return np.asarray(fit.intercept + fit.slope * years, dtype=np.float64)


def _loess_trend(years: np.ndarray, payoffs: np.ndarray, *, frac: float = 0.5) -> np.ndarray:
    """Locally weighted linear regression (Cleveland 1979) -- hand-rolled
    rather than pulling in statsmodels for one function: for each point,
    fit a line to its `frac`-fraction nearest neighbors (by year),
    weighted by the tricube kernel, and take that line's value at the
    point itself."""
    n = len(years)
    k = max(2, int(np.ceil(frac * n)))
    fitted = np.empty(n)
    for i in range(n):
        distances = np.abs(years - years[i])
        neighbor_idx = np.argsort(distances, kind="stable")[:k]
        d_max = distances[neighbor_idx].max()
        weights = np.ones(k) if d_max == 0 else (1 - (distances[neighbor_idx] / d_max) ** 3) ** 3
        design = np.column_stack([np.ones(k), years[neighbor_idx]])
        weighted_design = design * weights[:, None]
        beta = np.linalg.solve(
            design.T @ weighted_design, design.T @ (weights * payoffs[neighbor_idx])
        )
        fitted[i] = beta[0] + beta[1] * years[i]
    return fitted


def detrend_sample(
    sample: BurnSample, method: DetrendMethod, *, loess_frac: float = 0.5
) -> DetrendedSample:
    """Removes a fitted trend from `sample`'s payoffs and re-centers the
    residuals to the trend's own fitted value at the most recent year
    (`sample.years` is always ascending -- see `build_burn_sample`), so
    the detrended series stays on the original mm scale and represents
    "this season's payoff distribution at today's trend level," not the
    sample's historical average level (SPEC §7.3's own stated point of
    detrending: a 30+-year sample may have drifted). `method="none"` is
    the identity transform (trend = the sample mean everywhere, so
    residual + recenter reproduces the input exactly) -- letting a
    caller always route through this function uniformly, including when
    comparing "none" against the other two via out-of-sample CRPS
    (`select_best_detrend` below)."""
    if len(sample.payoffs) < 2:
        raise ValueError(
            f"need at least 2 historical seasons to fit a trend, got {len(sample.payoffs)}"
        )
    years = np.array(sample.years, dtype=float)
    payoffs = np.array(sample.payoffs, dtype=float)
    if method == "none":
        trend = np.full_like(payoffs, payoffs.mean())
    elif method == "linear":
        trend = _linear_trend(years, payoffs)
    else:
        trend = _loess_trend(years, payoffs, frac=loess_frac)
    recentered = (payoffs - trend) + trend[-1]
    return DetrendedSample(
        contract_code=sample.contract_code,
        method=method,
        years=sample.years,
        payoffs=[float(v) for v in recentered],
    )
