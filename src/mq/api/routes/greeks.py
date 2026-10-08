"""`GET /v1/series/{id}/greeks` (SPEC §9.2): delta/gamma/theta + SE —
M9's real Greeks (`mq.risk.greeks`), run against a real fitted chain
model (the same `mq.api.common.fit_real_chain_model` pipeline
`/v1/scenarios/run` uses).

**Corrects the same earlier wrong claim `/v1/scenarios/run` already
corrected** (see `docs/methods/api.md` §5): this route was listed as
blocked on "no reusable model-fitting pipeline." That pipeline exists
and is fast (~8s all-in, confirmed by timing it); building this route
only needed wiring Greeks' own bump-and-reprice calls onto it, which is
what this file does.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import polars as pl
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
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
from mq.pricing.simulator_glm import ChainModel
from mq.pricing.simulator_ref import SimRequest, calibrate_overdispersion_sd
from mq.risk.greeks import GreekResult, delta, gamma, theta_climatological_day, theta_no_rain_day

router = APIRouter(prefix="/v1/series", tags=["series"])

# Same model-fit cache shape as scenarios.py's, intentionally NOT
# shared across the two modules -- each route owns its own small cache
# rather than introducing cross-module coupling for it, the same choice
# hedge/parametric/scenarios each made for their own response caches.
_ModelCacheEntry = tuple[ChainModel, DailyLPA, float, float, float, pl.DataFrame]
_model_cache: dict[tuple[str, str], _ModelCacheEntry] = {}


def _now_meta(**kwargs: Any) -> Meta:
    return Meta(generated_at=datetime.now(UTC), **kwargs)


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

    official_values = official_index_values(spec, rain_grid)
    target_sd = float(np.std(list(official_values.values()), ddof=1))
    template_start = as_of + timedelta(days=1)
    sigma = calibrate_overdispersion_sd(
        model,
        daily_lpa,
        SimRequest(
            n_paths=4000,
            start_date=template_start,
            n_days=91,
            seed=42,
            observed_to_date=0.0,
            start_state=1,
            covariates=[mean_oni, mean_dmi],
        ),
        target_seasonal_total_sd=target_sd,
    )
    entry: _ModelCacheEntry = (model, daily_lpa, mean_oni, mean_dmi, sigma, climate_idx)
    _model_cache[cache_key] = entry
    return entry


class GreekResultData(BaseModel):
    value: float
    se: float
    se_fraction: float
    pairing: str
    note: str


class GreeksData(BaseModel):
    series_id: str
    n_paths: int
    observed_to_date: float
    start_date: str
    period_end: str
    delta: GreekResultData
    gamma: GreekResultData
    theta_no_rain_day: GreekResultData | None
    theta_climatological_day: GreekResultData | None


def _to_data(r: GreekResult) -> GreekResultData:
    return GreekResultData(
        value=r.value, se=r.se, se_fraction=r.se_fraction, pairing=r.pairing, note=r.note
    )


@router.get("/{series_id}/greeks")
def get_greeks(
    series_id: str,
    observed_to_date: float | None = Query(default=None),
    start_date: date | None = Query(default=None),
    start_state: int = Query(default=1, ge=0, le=1),
    n_paths: int = Query(default=20_000, gt=0, le=200_000),
    seed: int = Query(default=42),
    bump_mm: float = Query(default=10.0, gt=0),
    as_of: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Envelope[GreeksData]:
    """Real M9 Greeks: delta/gamma via common random numbers (exact CRN
    pairing -- structurally delta=1.0/gamma=0 for this CDR index, see
    `docs/methods/greeks.md`), theta via the two partial-pairing bump
    scenarios (no-rain-day / climatological-day), each reporting its own
    standard error and SE-as-fraction-of-value per SPEC's SE<5% bar.
    theta is omitted (not computed) when `start_date >= period_end`,
    since there's no remaining season to bump a day into.

    `n_paths` capped at 200k per SPEC; higher `n_paths` is what actually
    lets theta meet the SE<5% bar in practice (`docs/methods/greeks.md`'s
    real run needed ~1,000,000 paths via the C++ core at n_paths that
    large -- this route still uses the NumPy-level `mq.risk.greeks`
    functions, so very large `n_paths` here will be proportionally
    slower; no request-hash cache yet, unlike the POSTs, since repeated
    identical GETs are a smaller concern than this endpoint's real
    per-call cost)."""
    contract_code = db.execute(
        select(Contract.contract_code).where(Contract.series_id == series_id)
    ).scalar_one_or_none()
    if contract_code is None:
        raise unknown_series(series_id)
    period_end = db.execute(
        select(Contract.period_end).where(Contract.series_id == series_id)
    ).scalar_one()
    if period_end is None:
        raise unknown_series(f"{series_id}: registered contract has no period_end")

    effective_as_of = as_of if as_of is not None else date.today()
    effective_start = start_date if start_date is not None else effective_as_of + timedelta(days=1)
    if effective_start > period_end:
        raise infeasible_hedge(
            f"{series_id}: start_date {effective_start} is after period_end {period_end} -- "
            "this season is already over"
        )

    effective_obs = observed_to_date
    if effective_obs is None:
        latest_index = db.execute(
            select(IndexValue)
            .where(IndexValue.series_id == series_id)
            .order_by(IndexValue.obs_date.desc(), IndexValue.as_of_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest_index is None or (
            latest_index.official_value is None and latest_index.proxy_value is None
        ):
            raise infeasible_hedge(
                f"{series_id}: no real index_values row to default observed_to_date from -- "
                "pass it explicitly"
            )
        effective_obs = float(
            latest_index.official_value
            if latest_index.official_value is not None
            else latest_index.proxy_value  # type: ignore[arg-type]
        )

    model, daily_lpa, mean_oni, mean_dmi, overdispersion_sd, _climate_idx = _get_or_fit_model(
        db, series_id, contract_code, effective_as_of
    )

    common_kwargs: dict[str, Any] = dict(
        observed_to_date=effective_obs,
        start_date=effective_start,
        period_end=period_end,
        start_state=start_state,
        covariates=[mean_oni, mean_dmi],
        overdispersion_sd=overdispersion_sd,
        n_paths=n_paths,
        seed=seed,
        bump_mm=bump_mm,
    )
    d = delta(model, daily_lpa, **common_kwargs)
    g = gamma(model, daily_lpa, **common_kwargs)

    theta1_data: GreekResultData | None = None
    theta2_data: GreekResultData | None = None
    if effective_start < period_end:
        theta_kwargs = {k: v for k, v in common_kwargs.items() if k != "bump_mm"}
        t1 = theta_no_rain_day(model, daily_lpa, **theta_kwargs)
        t2 = theta_climatological_day(model, daily_lpa, **theta_kwargs)
        theta1_data = _to_data(t1)
        theta2_data = _to_data(t2)

    data = GreeksData(
        series_id=series_id,
        n_paths=n_paths,
        observed_to_date=effective_obs,
        start_date=effective_start.isoformat(),
        period_end=period_end.isoformat(),
        delta=_to_data(d),
        gamma=_to_data(g),
        theta_no_rain_day=theta1_data,
        theta_climatological_day=theta2_data,
    )
    return Envelope(data=data, meta=_now_meta(as_of=effective_as_of))
