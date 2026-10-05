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

import polars as pl

from mq.index.engine import compute_index
from mq.index.lpa import DailyLPA
from mq.specs.contract import ContractSpec, MonthDay


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
