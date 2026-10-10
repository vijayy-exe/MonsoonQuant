"""`POST /v1/scenarios/run` (SPEC §9.2): scenario valuations — M11's
real scenario lab (`mq.risk.scenarios.run_scenario`) against a real
fitted chain model (M5.1/M5.2's real `fit_chain_model`, on real
station-averaged rainfall + real ONI/DMI covariates), not a toy.

**A real correction made while building this endpoint, worth stating
plainly**: `docs/STATUS.md` previously claimed `greeks`/`scenarios/run`
needed "a real model-fitting pipeline" that didn't exist yet. That was
wrong — `mq.pricing.simulator_glm.fit_chain_model` plus
`mq.forecasting.features.station_average_daily_series` and
`mq.pricing.simulator_glm.attach_monthly_covariate` already ARE a
complete, real, importable pipeline (confirmed by reading their source
and by timing a real fit: 0.08s for `fit_chain_model` itself, ~7s for
the daily-series prep it depends on, ~8s all-in with the parquet read
— same order of cost as `hedge`/`parametric/design`, not a missing
capability). What was actually missing was a convenience function
wiring the pieces together outside a one-off `.scratch/*_demo.py`
script, which is exactly what `mq.api.common.fit_real_chain_model` now
is.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

import numpy as np
import polars as pl
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from mq.api.common import (
    fit_real_chain_model,
    load_climate_idx,
    load_rain_grid,
    load_resolved_spec,
    official_index_values,
)
from mq.api.deps import get_db
from mq.api.errors import infeasible_hedge, unknown_series
from mq.api.schemas.envelope import Envelope, Meta
from mq.db.models import Contract, IndexValue
from mq.index.lpa import DailyLPA
from mq.pricing.distribution import oni_terciles, season_oni
from mq.pricing.simulator_glm import ChainModel
from mq.pricing.simulator_ref import SimRequest, calibrate_overdispersion_sd
from mq.risk.scenarios import (
    ScenarioShock,
    cloudburst,
    dry_november,
    el_nino,
    historical_analog,
    la_nina,
    negative_iod,
    neutral_enso,
    positive_iod,
    run_scenario,
)

router = APIRouter(prefix="/v1/scenarios", tags=["scenarios"])

_ShockName = Literal[
    "el_nino",
    "la_nina",
    "neutral_enso",
    "positive_iod",
    "negative_iod",
    "dry_november",
    "cloudburst",
]
_SHOCK_FACTORIES: dict[str, Any] = {
    "el_nino": el_nino,
    "la_nina": la_nina,
    "neutral_enso": neutral_enso,
    "positive_iod": positive_iod,
    "negative_iod": negative_iod,
    "dry_november": dry_november,
    "cloudburst": cloudburst,
}
_ALL_SHOCK_NAMES: list[_ShockName] = [
    "el_nino",
    "la_nina",
    "neutral_enso",
    "positive_iod",
    "negative_iod",
    "dry_november",
    "cloudburst",
]


def _now_meta(**kwargs: Any) -> Meta:
    return Meta(generated_at=datetime.now(UTC), **kwargs)


# Model-fit cache: the real chain-model fit + calibrated overdispersion
# are identical for every scenario request against the same
# (contract_code, as_of) -- the real cost (~8s: parquet reads + the
# daily-covariate join) is paid once per key, not once per request, and
# definitely not once per shock within a request.
_ModelCacheEntry = tuple[
    ChainModel, DailyLPA, float, float, float, pl.DataFrame, dict[int, float], dict[int, float]
]
_model_cache: dict[tuple[str, str], _ModelCacheEntry] = {}

# Full-response cache, keyed by request hash -- SPEC's own stated
# pattern for the heavy POSTs.
_scenarios_cache: dict[tuple[Any, ...], dict[str, Any]] = {}


class ScenariosRunRequest(BaseModel):
    series_id: str
    shocks: list[_ShockName] = Field(default_factory=lambda: list(_ALL_SHOCK_NAMES))
    historical_analog_years: list[int] = Field(
        default_factory=list,
        description="Real ONI/DMI from these real historical years (e.g. 2015 for SPEC's "
        "Chennai-floods analog), from the real ingested climate_idx data",
    )
    observed_to_date: float | None = Field(
        default=None,
        description="CDR spot already accumulated before start_date; defaults to the latest "
        "real index_values row for this series",
    )
    start_date: date | None = Field(default=None, description="Defaults to the day after `as_of`")
    start_state: int = Field(
        default=1, ge=0, le=1, description="0=dry, 1=wet, day before start_date"
    )
    n_paths: int = Field(
        default=20_000, gt=0, le=200_000, description="SPEC's n_paths cap enforced"
    )
    seed: int = 42
    hedge_lots: int | None = None
    hedge_multiplier: float | None = None
    as_of: date | None = None


class ScenarioRunResultData(BaseModel):
    name: str
    description: str
    valuations: dict[str, float]
    greeks: dict[str, float]
    hedge_pnl: float | None
    hedge_pnl_note: str


class ScenariosRunData(BaseModel):
    series_id: str
    n_paths: int
    observed_to_date: float
    start_date: str
    period_end: str
    overdispersion_sd: float
    results: list[ScenarioRunResultData]


def _request_cache_key(req: ScenariosRunRequest, effective_as_of: date) -> tuple[Any, ...]:
    return (
        req.series_id,
        effective_as_of.isoformat(),
        tuple(sorted(req.shocks)),
        tuple(sorted(req.historical_analog_years)),
        req.observed_to_date,
        req.start_date.isoformat() if req.start_date else None,
        req.start_state,
        req.n_paths,
        req.seed,
        req.hedge_lots,
        req.hedge_multiplier,
    )


def _get_or_fit_model(
    db: Session, series_id: str, contract_code: str, as_of: date
) -> _ModelCacheEntry:
    cache_key = (contract_code, as_of.isoformat())
    cached = _model_cache.get(cache_key)
    if cached is not None:
        return cached

    spec = load_resolved_spec(db, series_id, contract_code)
    rain_grid = load_rain_grid(as_of)
    climate_idx = load_climate_idx(as_of)
    model, daily_lpa, mean_oni, mean_dmi = fit_real_chain_model(spec, rain_grid, climate_idx)

    # Calibrate the real season-level overdispersion against the real
    # official index's own observed season-to-season spread (its sd) --
    # not a hardcoded illustrative constant like `.scratch/scenarios_
    # demo.py` used, a real calibration against real data.
    official_values = official_index_values(spec, rain_grid)
    target_sd = float(np.std(list(official_values.values()), ddof=1))
    template_start = as_of + timedelta(days=1)
    template_end = max(template_start, template_start + timedelta(days=90))
    sigma = calibrate_overdispersion_sd(
        model,
        daily_lpa,
        SimRequest(
            n_paths=4000,
            start_date=template_start,
            n_days=(template_end - template_start).days + 1,
            seed=42,
            observed_to_date=0.0,
            start_state=1,
            covariates=[mean_oni, mean_dmi],
        ),
        target_seasonal_total_sd=target_sd,
    )

    # Real per-year ONI (for SPEC §7.12's ENSO-conditioned burn
    # valuation, run_scenario's optional historical_payoffs/year_oni
    # args) -- cheap: climate_idx is already loaded and small, and this
    # is paid once per (contract_code, as_of), same as everything else
    # in this cache entry.
    oni_rows = climate_idx.filter(pl.col("index") == "oni")
    year_oni = {
        y: v for y in official_values for v in [season_oni(oni_rows, year=y)] if v is not None
    }

    entry: _ModelCacheEntry = (
        model,
        daily_lpa,
        mean_oni,
        mean_dmi,
        sigma,
        climate_idx,
        official_values,
        year_oni,
    )
    _model_cache[cache_key] = entry
    return entry


@router.post("/run")
def post_scenarios_run(
    req: ScenariosRunRequest, db: Session = Depends(get_db)
) -> Envelope[ScenariosRunData]:
    """Real M11 scenario lab: each named shock (ENSO/IOD presets, a
    cloudburst bump, or a real historical-year ONI/DMI analog) re-runs
    the real simulator + Greeks under the shocked covariates, against a
    real fitted chain model. Cached by request hash (SPEC §9.3);
    `n_paths` capped at 200k per SPEC."""
    contract_code = db.execute(
        select(Contract.contract_code).where(Contract.series_id == req.series_id)
    ).scalar_one_or_none()
    if contract_code is None:
        raise unknown_series(req.series_id)
    period_end = db.execute(
        select(Contract.period_end).where(Contract.series_id == req.series_id)
    ).scalar_one()
    if period_end is None:
        raise unknown_series(f"{req.series_id}: registered contract has no period_end")

    effective_as_of = req.as_of if req.as_of is not None else date.today()
    cache_key = _request_cache_key(req, effective_as_of)
    cached = _scenarios_cache.get(cache_key)
    if cached is not None:
        return Envelope(
            data=ScenariosRunData.model_validate(cached), meta=_now_meta(as_of=effective_as_of)
        )

    start_date = (
        req.start_date if req.start_date is not None else effective_as_of + timedelta(days=1)
    )
    if start_date > period_end:
        raise infeasible_hedge(
            f"{req.series_id}: start_date {start_date} is after the series' own period_end "
            f"{period_end} -- this season is already over"
        )

    observed_to_date = req.observed_to_date
    if observed_to_date is None:
        latest_index = db.execute(
            select(IndexValue)
            .where(IndexValue.series_id == req.series_id)
            .order_by(IndexValue.obs_date.desc(), IndexValue.as_of_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest_index is None or (
            latest_index.official_value is None and latest_index.proxy_value is None
        ):
            raise infeasible_hedge(
                f"{req.series_id}: no real index_values row to default observed_to_date from -- "
                "pass it explicitly"
            )
        observed_to_date = float(
            latest_index.official_value
            if latest_index.official_value is not None
            else latest_index.proxy_value  # type: ignore[arg-type]
        )

    (
        model,
        daily_lpa,
        mean_oni,
        mean_dmi,
        overdispersion_sd,
        climate_idx,
        official_values,
        year_oni,
    ) = _get_or_fit_model(db, req.series_id, contract_code, effective_as_of)
    year_terciles = oni_terciles(year_oni) if year_oni else {}
    historical_years = sorted(year_oni) if year_oni else None
    historical_payoffs = (
        np.array([official_values[y] for y in historical_years])
        if historical_years is not None
        else None
    )
    rng = np.random.default_rng(req.seed)

    shocks: list[ScenarioShock] = [_SHOCK_FACTORIES[name]() for name in req.shocks]
    for year in req.historical_analog_years:
        shocks.append(historical_analog(climate_idx, year=year))
    if not shocks:
        raise infeasible_hedge("at least one shock (named or historical_analog_years) is required")

    results = []
    for shock in shocks:
        r = run_scenario(
            model,
            daily_lpa,
            shock,
            observed_to_date=observed_to_date,
            start_date=start_date,
            period_end=period_end,
            start_state=req.start_state,
            covariates=[mean_oni, mean_dmi],
            overdispersion_sd=overdispersion_sd,
            n_paths=req.n_paths,
            seed=req.seed,
            hedge_lots=req.hedge_lots,
            hedge_multiplier=req.hedge_multiplier,
            historical_payoffs=historical_payoffs,
            historical_years=historical_years,
            year_oni=year_oni or None,
            year_terciles=year_terciles or None,
            rng=rng,
        )
        results.append(
            ScenarioRunResultData(
                name=r.scenario.name,
                description=r.scenario.description,
                valuations=r.valuations,
                greeks=r.greeks,
                hedge_pnl=r.hedge_pnl,
                hedge_pnl_note=r.hedge_pnl_note,
            )
        )

    data = ScenariosRunData(
        series_id=req.series_id,
        n_paths=req.n_paths,
        observed_to_date=observed_to_date,
        start_date=start_date.isoformat(),
        period_end=period_end.isoformat(),
        overdispersion_sd=overdispersion_sd,
        results=results,
    )
    _scenarios_cache[cache_key] = data.model_dump(mode="json")
    return Envelope(data=data, meta=_now_meta(as_of=effective_as_of))
