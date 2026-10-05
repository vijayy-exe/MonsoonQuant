"""Scenario lab (SPEC §7.12).

Each preset perturbs model INPUTS (ONI/DMI covariates, `observed_to_date`,
or a direct historical-analog substitution) and re-runs the
already-built pricing/Greeks/hedge pipeline under that perturbation —
**this module adds no new pricing math**, it's an orchestration layer
over M5 (simulator), M9 (Greeks), and an optional existing hedge
position (M9's hedge optimiser), answering "what if?" rather than
computing anything new.

**ENSO/IOD presets** shock the ONI/DMI covariates fed to the chain
model's GLM (M5.1) directly — real values the fitted model was trained
on, not synthetic placeholders.

**"2015 Chennai floods analog"** uses the *real* 2015 ONI/DMI values
(from `mq.pipelines.climate_idx`'s real ingested data), not an
illustrative shock — 2015 was a real, strong El Niño year in this
project's own backtest record (`docs/methods/forecasting.md`), so this
preset is genuinely historically grounded, unlike the others.

**"Dry November" and "+100mm cloudburst tomorrow"** are the two SPEC
names that don't map onto a covariate the chain model actually has — the
model's seasonality already comes from Fourier harmonics of
day-of-year, not a separate month-level dial, so "dry November" is
implemented as an illustrative ONI/DMI shock toward the dry end (SPEC's
own "custom shock" escape hatch generalizes this), clearly labelled as
an approximation rather than a literal "only November is dry" shock.
"+100mm cloudburst tomorrow" is exact, not approximate: it's a direct
`observed_to_date` bump, using the identical mechanism `mq.risk.greeks`
already relies on (a pure additive offset that never touches the RNG).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import polars as pl

from mq.index.lpa import DailyLPA
from mq.pricing.simulator_glm import ChainModel
from mq.risk.greeks import (
    delta,
    full_season_payoff,
    gamma,
    theta_climatological_day,
    theta_no_rain_day,
)


@dataclass(frozen=True)
class ScenarioShock:
    name: str
    description: str
    oni_override: float | None = None
    dmi_override: float | None = None
    observed_to_date_bump_mm: float = 0.0
    is_historical_analog: bool = False


def el_nino(*, oni: float = 2.0) -> ScenarioShock:
    return ScenarioShock(
        name="el_nino", description=f"Strong El Nino (ONI={oni:+.1f})", oni_override=oni
    )


def la_nina(*, oni: float = -1.5) -> ScenarioShock:
    return ScenarioShock(
        name="la_nina", description=f"Strong La Nina (ONI={oni:+.1f})", oni_override=oni
    )


def neutral_enso() -> ScenarioShock:
    return ScenarioShock(
        name="neutral_enso", description="Neutral ENSO (ONI=0.0)", oni_override=0.0
    )


def positive_iod(*, dmi: float = 0.8) -> ScenarioShock:
    return ScenarioShock(
        name="positive_iod", description=f"Positive IOD (DMI={dmi:+.1f})", dmi_override=dmi
    )


def negative_iod(*, dmi: float = -0.8) -> ScenarioShock:
    return ScenarioShock(
        name="negative_iod", description=f"Negative IOD (DMI={dmi:+.1f})", dmi_override=dmi
    )


def dry_november(*, oni: float = -1.0, dmi: float = -0.5) -> ScenarioShock:
    """Illustrative, not literal — see module docstring: the chain
    model has no month-specific dial beyond its Fourier seasonality, so
    this approximates "a dry late season" via a dry-leaning ENSO/IOD
    shock rather than a direct November-only intervention."""
    return ScenarioShock(
        name="dry_november",
        description="Illustrative dry-leaning shock (approximates a dry late season)",
        oni_override=oni,
        dmi_override=dmi,
    )


def cloudburst(*, bump_mm: float = 100.0) -> ScenarioShock:
    return ScenarioShock(
        name="cloudburst",
        description=f"+{bump_mm:.0f}mm cloudburst tomorrow",
        observed_to_date_bump_mm=bump_mm,
    )


def custom_shock(
    *,
    name: str,
    description: str,
    oni: float | None = None,
    dmi: float | None = None,
    bump_mm: float = 0.0,
) -> ScenarioShock:
    return ScenarioShock(
        name=name,
        description=description,
        oni_override=oni,
        dmi_override=dmi,
        observed_to_date_bump_mm=bump_mm,
    )


def historical_analog(climate_idx: pl.DataFrame, *, year: int, month: int = 9) -> ScenarioShock:
    """A named historical year's REAL ONI/DMI (e.g. 2015 for SPEC's
    "Chennai floods analog") rather than an illustrative override —
    genuinely grounded in the real ingested climate_idx data, not a
    placeholder."""
    oni_row = climate_idx.filter(
        (pl.col("index") == "oni")
        & (pl.col("date").dt.year() == year)
        & (pl.col("date").dt.month() == month)
    )
    dmi_row = climate_idx.filter(
        (pl.col("index") == "dmi")
        & (pl.col("date").dt.year() == year)
        & (pl.col("date").dt.month() == month)
    )
    if oni_row.height == 0 or dmi_row.height == 0:
        raise ValueError(f"no real ONI/DMI data for year={year} month={month}")
    oni_val = float(oni_row["value"][0])
    dmi_val = float(dmi_row["value"][0])
    return ScenarioShock(
        name=f"historical_analog_{year}",
        description=f"Real {year} ONI={oni_val:+.2f} DMI={dmi_val:+.2f} analog",
        oni_override=oni_val,
        dmi_override=dmi_val,
        is_historical_analog=True,
    )


@dataclass(frozen=True)
class ScenarioResult:
    scenario: ScenarioShock
    valuations: dict[str, float]
    greeks: dict[str, float]
    hedge_pnl: float | None = None
    hedge_pnl_note: str = ""


def _apply_shock(covariates: list[float], shock: ScenarioShock) -> list[float]:
    effective = list(covariates)
    if shock.oni_override is not None and len(effective) >= 1:
        effective[0] = shock.oni_override
    if shock.dmi_override is not None and len(effective) >= 2:
        effective[1] = shock.dmi_override
    return effective


def run_scenario(
    model: ChainModel,
    daily_lpa: DailyLPA,
    shock: ScenarioShock,
    *,
    observed_to_date: float,
    start_date: date,
    period_end: date,
    start_state: int,
    covariates: list[float],
    overdispersion_sd: float,
    n_paths: int,
    seed: int,
    hedge_lots: int | None = None,
    hedge_multiplier: float | None = None,
) -> ScenarioResult:
    """`covariates` must be `[oni, dmi]` (the order the real chain model
    uses, M5.1/M5.2) for `oni_override`/`dmi_override` to land correctly
    -- a model fit with different/more covariates needs its own
    shock-application logic, not supported generically here."""
    effective_covariates = _apply_shock(covariates, shock)
    effective_obs = observed_to_date + shock.observed_to_date_bump_mm

    common: dict[str, Any] = dict(
        observed_to_date=effective_obs,
        start_date=start_date,
        period_end=period_end,
        start_state=start_state,
        covariates=effective_covariates,
        overdispersion_sd=overdispersion_sd,
        n_paths=n_paths,
        seed=seed,
    )

    payoff = full_season_payoff(model, daily_lpa, **common)
    valuations = {
        "simulator_mean": float(np.mean(payoff)),
        "simulator_p5": float(np.quantile(payoff, 0.05)),
        "simulator_p95": float(np.quantile(payoff, 0.95)),
    }

    d = delta(model, daily_lpa, **common)
    g = gamma(model, daily_lpa, **common)
    greeks = {"delta": d.value, "gamma": g.value}
    if start_date < period_end:
        t1 = theta_no_rain_day(model, daily_lpa, **common)
        t2 = theta_climatological_day(model, daily_lpa, **common)
        greeks["theta_no_rain_day"] = t1.value
        greeks["theta_climatological_day"] = t2.value

    hedge_pnl = None
    hedge_pnl_note = ""
    if hedge_lots is not None and hedge_multiplier is not None:
        hedge_pnl = hedge_lots * hedge_multiplier * valuations["simulator_mean"]
        hedge_pnl_note = (
            "P&L of an EXISTING hedge position (held at `hedge_lots`) if the index settles at "
            "this scenario's mean simulated payoff -- not a re-optimized hedge for this scenario."
        )

    return ScenarioResult(
        scenario=shock,
        valuations=valuations,
        greeks=greeks,
        hedge_pnl=hedge_pnl,
        hedge_pnl_note=hedge_pnl_note,
    )


def standard_presets() -> list[ScenarioShock]:
    return [
        el_nino(),
        la_nina(),
        neutral_enso(),
        positive_iod(),
        negative_iod(),
        dry_november(),
        cloudburst(),
    ]
