"""Model sensitivities (SPEC §7.8) — NOT exchange-standard Greeks: these
are finite-difference bumps of this project's own simulator-based fair
value, labelled explicitly as such rather than implying a
market-calibrated options-Greek interpretation.

    delta = [V(obs+dr) - V(obs-dr)] / (2*dr)      dr = 10mm, configurable
    gamma = [V(obs+dr) - 2*V(obs) + V(obs-dr)] / dr**2
    theta = V(t+1 | no-rain day) - V(t)   and   V(t+1 | climatological day) - V(t)

**Common random numbers (CRN)**: without it, two independent Monte
Carlo estimates of V differ by MC noise that swamps a genuinely small
sensitivity. `observed_to_date` is a pure additive offset on
`terminal_index` in both simulator backends (M5) — it never touches any
RNG draw — so delta/gamma automatically get *exact* path-for-path CRN
pairing from reusing one seed: `V(obs+dr)` and `V(obs-dr)` share
identical per-path noise, and only the deterministic `obs` shift
differs. Theta's two bumped valuations instead shift `start_date` by a
day, which *does* change which calendar day lands at RNG day-index 0 —
so its CRN pairing is not perfect (the season-level overdispersion
multiplier is still shared, since it depends only on (seed, path_id),
but the day-by-day draws are not identically paired) — reported
honestly as `pairing="exact"` vs `pairing="partial"` on each result
rather than claimed uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from mq.index.lpa import DailyLPA, daily_lpa_lookup
from mq.pricing.simulator_glm import ChainModel
from mq.pricing.simulator_ref import SimRequest
from mq.pricing.simulator_ref import simulate as simulate_numpy

DEFAULT_BUMP_MM = 10.0


@dataclass(frozen=True)
class GreekResult:
    name: str
    value: float
    se: float
    se_fraction: float  # |se / value|; SPEC's acceptance bar is < 0.05
    pairing: str  # "exact" (delta/gamma) or "partial" (theta) -- see module docstring
    note: str = "model sensitivity, not an exchange-standard Greek"


def full_season_payoff(
    model: ChainModel,
    daily_lpa: DailyLPA,
    *,
    observed_to_date: float,
    start_date: date,
    period_end: date,
    start_state: int,
    covariates: list[float],
    overdispersion_sd: float,
    n_paths: int,
    seed: int,
) -> np.ndarray:
    """One simulated terminal-payoff value per path, for the remaining
    season [start_date, period_end] — the valuation function `V` that
    every Greek below bumps."""
    n_days = (period_end - start_date).days + 1
    if n_days <= 0:
        raise ValueError(f"start_date={start_date} is not before/at period_end={period_end}")
    req = SimRequest(
        n_paths=n_paths,
        start_date=start_date,
        n_days=n_days,
        seed=seed,
        observed_to_date=observed_to_date,
        start_state=start_state,
        covariates=covariates,
        overdispersion_sd=overdispersion_sd,
    )
    return simulate_numpy(model, daily_lpa, req).terminal_index


def delta(
    model: ChainModel,
    daily_lpa: DailyLPA,
    *,
    observed_to_date: float,
    start_date: date,
    period_end: date,
    start_state: int,
    covariates: list[float],
    overdispersion_sd: float,
    n_paths: int,
    seed: int,
    bump_mm: float = DEFAULT_BUMP_MM,
) -> GreekResult:
    def v(obs: float) -> np.ndarray:
        return full_season_payoff(
            model,
            daily_lpa,
            observed_to_date=obs,
            start_date=start_date,
            period_end=period_end,
            start_state=start_state,
            covariates=covariates,
            overdispersion_sd=overdispersion_sd,
            n_paths=n_paths,
            seed=seed,  # SAME seed -> exact CRN pairing (obs never touches the RNG)
        )

    plus = v(observed_to_date + bump_mm)
    minus = v(observed_to_date - bump_mm)
    per_path = (plus - minus) / (2.0 * bump_mm)
    return _summarize("delta", per_path, pairing="exact")


def gamma(
    model: ChainModel,
    daily_lpa: DailyLPA,
    *,
    observed_to_date: float,
    start_date: date,
    period_end: date,
    start_state: int,
    covariates: list[float],
    overdispersion_sd: float,
    n_paths: int,
    seed: int,
    bump_mm: float = DEFAULT_BUMP_MM,
) -> GreekResult:
    def v(obs: float) -> np.ndarray:
        return full_season_payoff(
            model,
            daily_lpa,
            observed_to_date=obs,
            start_date=start_date,
            period_end=period_end,
            start_state=start_state,
            covariates=covariates,
            overdispersion_sd=overdispersion_sd,
            n_paths=n_paths,
            seed=seed,
        )

    plus = v(observed_to_date + bump_mm)
    mid = v(observed_to_date)
    minus = v(observed_to_date - bump_mm)
    per_path = (plus - 2.0 * mid + minus) / (bump_mm**2)
    return _summarize("gamma", per_path, pairing="exact")


def theta_no_rain_day(
    model: ChainModel,
    daily_lpa: DailyLPA,
    *,
    observed_to_date: float,
    start_date: date,
    period_end: date,
    start_state: int,
    covariates: list[float],
    overdispersion_sd: float,
    n_paths: int,
    seed: int,
) -> GreekResult:
    """V(t+1 | tomorrow is confirmed dry) - V(t): tomorrow's deviation
    is exactly -lpa_mm(tomorrow) (zero rain), so the bumped valuation's
    `observed_to_date` is reduced by that known constant and its horizon
    shortens by one day."""
    lpa_by_day = daily_lpa_lookup(daily_lpa)
    try:
        lpa_tomorrow = lpa_by_day[(start_date.month, start_date.day)]
    except KeyError as exc:
        raise ValueError(f"no LPA value for calendar day {exc.args[0]}") from exc

    v_t = full_season_payoff(
        model,
        daily_lpa,
        observed_to_date=observed_to_date,
        start_date=start_date,
        period_end=period_end,
        start_state=start_state,
        covariates=covariates,
        overdispersion_sd=overdispersion_sd,
        n_paths=n_paths,
        seed=seed,
    )
    if start_date + timedelta(days=1) > period_end:
        # no days remain after "tomorrow" -- the bumped valuation is
        # just the deterministic payoff on expiry, no further simulation.
        v_t1 = np.full(n_paths, observed_to_date - lpa_tomorrow)
    else:
        v_t1 = full_season_payoff(
            model,
            daily_lpa,
            observed_to_date=observed_to_date - lpa_tomorrow,
            start_date=start_date + timedelta(days=1),
            period_end=period_end,
            start_state=0,  # confirmed dry
            covariates=covariates,
            overdispersion_sd=overdispersion_sd,
            n_paths=n_paths,
            seed=seed,  # shared season_effect; day draws shift by a day -- partial CRN
        )
    diff = v_t1.mean() - v_t.mean()
    se = float(np.sqrt(v_t1.var(ddof=1) / n_paths + v_t.var(ddof=1) / n_paths))
    return GreekResult(
        name="theta_no_rain_day",
        value=float(diff),
        se=se,
        se_fraction=abs(se / diff) if diff != 0 else float("inf"),
        pairing="partial",
    )


def theta_climatological_day(
    model: ChainModel,
    daily_lpa: DailyLPA,
    *,
    observed_to_date: float,
    start_date: date,
    period_end: date,
    start_state: int,
    covariates: list[float],
    overdispersion_sd: float,
    n_paths: int,
    seed: int,
) -> GreekResult:
    """V(t+1 | tomorrow rains exactly its own LPA) - V(t): a
    climatological day has deviation=0 by definition, so `observed_to_date`
    is unchanged and only the horizon shortens by one day."""
    v_t = full_season_payoff(
        model,
        daily_lpa,
        observed_to_date=observed_to_date,
        start_date=start_date,
        period_end=period_end,
        start_state=start_state,
        covariates=covariates,
        overdispersion_sd=overdispersion_sd,
        n_paths=n_paths,
        seed=seed,
    )
    if start_date + timedelta(days=1) > period_end:
        v_t1 = np.full(n_paths, observed_to_date)
    else:
        v_t1 = full_season_payoff(
            model,
            daily_lpa,
            observed_to_date=observed_to_date,
            start_date=start_date + timedelta(days=1),
            period_end=period_end,
            start_state=start_state,
            covariates=covariates,
            overdispersion_sd=overdispersion_sd,
            n_paths=n_paths,
            seed=seed,
        )
    diff = v_t1.mean() - v_t.mean()
    se = float(np.sqrt(v_t1.var(ddof=1) / n_paths + v_t.var(ddof=1) / n_paths))
    return GreekResult(
        name="theta_climatological_day",
        value=float(diff),
        se=se,
        se_fraction=abs(se / diff) if diff != 0 else float("inf"),
        pairing="partial",
    )


def _summarize(name: str, per_path: np.ndarray, *, pairing: str) -> GreekResult:
    value = float(np.mean(per_path))
    se = float(np.std(per_path, ddof=1) / np.sqrt(len(per_path)))
    return GreekResult(
        name=name,
        value=value,
        se=se,
        se_fraction=abs(se / value) if value != 0 else float("inf"),
        pairing=pairing,
    )
