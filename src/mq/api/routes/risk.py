"""`POST /v1/hedge` (SPEC §9.2): optimal lots, effectiveness, residual
risk — M9's real min-variance and CVaR95 hedge optimisers, run against
a real candidate exposure location's local rainfall and the real
official contract index, not synthetic scenarios.

**The exposure itself stays explicitly synthetic/illustrative, same
posture as SPEC's own §7.11 case study and M9's `docs/methods/hedge.md`
real run**: SPEC's four named exposure templates (delivery-rider,
crop-yield, event-cancellation, construction-downtime) aren't
calibrated to any real business, only their shape is real. What's real
here: the candidate location's actual IMD rainfall, the real official
RAINCHNNAI/RAINMUMBAI index built from it, and the real optimiser math
run against that real data — a caller supplies a real location and a
chosen illustrative exposure shape; the engine does nothing synthetic
with either.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from mq.api.common import load_rain_grid, load_resolved_spec, official_index_values
from mq.api.deps import get_db
from mq.api.errors import infeasible_hedge, unknown_series
from mq.api.schemas.envelope import Envelope, Meta
from mq.db.models import Contract
from mq.risk.basis import local_index_series
from mq.risk.cvar import minimize_cvar_hedge
from mq.risk.hedge import (
    LotConstraints,
    PiecewiseLinearExposure,
    construction_downtime_loss,
    crop_yield_loss,
    delivery_rider_income_loss,
    event_cancellation_loss,
    min_variance_hedge,
)

router = APIRouter(prefix="/v1", tags=["risk"])

_ExposureTemplateFn = Callable[..., PiecewiseLinearExposure]
_EXPOSURE_TEMPLATES: dict[str, _ExposureTemplateFn] = {
    "delivery_rider": delivery_rider_income_loss,
    "crop_yield": crop_yield_loss,
    "event_cancellation": event_cancellation_loss,
    "construction_downtime": construction_downtime_loss,
}


def _now_meta(**kwargs: Any) -> Meta:
    return Meta(generated_at=datetime.now(UTC), **kwargs)


# Process-lifetime cache keyed by the full request hash -- SPEC's own
# stated pattern for the heavy POSTs. The dominant real cost here is
# the shared 31-year official-index reconstruction (~8s, same as
# basis's -- see mq.api.common/routes/series.py's basis cache note) plus
# one single-location CDR reconstruction (cheap relative to basis_grid's
# full multi-cell scan), so an uncached call is a few seconds, not
# basis's ~48s -- still real work worth not repeating for an identical
# request.
_hedge_cache: dict[tuple[Any, ...], dict[str, Any]] = {}


class HedgeConstraints(BaseModel):
    max_order_lots: int | None = None
    position_limit_lots: int | None = None
    margin_budget: float | None = None
    margin_per_lot: float | None = None
    max_notional: float | None = None
    notional_per_lot: float | None = None
    long_allowed: bool = True
    short_allowed: bool = True


class HedgeRequest(BaseModel):
    series_id: str
    location_lat: float = Field(..., ge=-90, le=90)
    location_lon: float = Field(..., ge=-180, le=180)
    exposure_template: Literal[
        "delivery_rider", "crop_yield", "event_cancellation", "construction_downtime"
    ] = "delivery_rider"
    template_params: dict[str, float] = Field(default_factory=dict)
    multiplier: float | None = Field(
        default=None, description="INR per index point; defaults to the contract's own spec value"
    )
    constraints: HedgeConstraints = Field(default_factory=HedgeConstraints)
    alpha: float = Field(default=0.95, gt=0, lt=1)
    as_of: date | None = None


class MinVarianceResult(BaseModel):
    h_star: float
    lots: int
    h_realized: float
    hedge_effectiveness: float
    residual_variance: float
    do_nothing_variance: float
    basis_contribution: float


class Cvar95Result(BaseModel):
    h_star: float
    lots: int
    h_realized: float
    cvar_95: float
    do_nothing_cvar_95: float
    var_95: float


class HedgeResponseData(BaseModel):
    series_id: str
    n_years: int
    location: dict[str, float]
    exposure_template: str
    multiplier: float
    min_variance: MinVarianceResult
    cvar95: Cvar95Result


def _request_cache_key(req: HedgeRequest, effective_as_of: date) -> tuple[Any, ...]:
    return (
        req.series_id,
        effective_as_of.isoformat(),
        round(req.location_lat, 6),
        round(req.location_lon, 6),
        req.exposure_template,
        tuple(sorted(req.template_params.items())),
        req.multiplier,
        req.constraints.model_dump_json(),
        req.alpha,
    )


@router.post("/hedge")
def post_hedge(req: HedgeRequest, db: Session = Depends(get_db)) -> Envelope[HedgeResponseData]:
    """Real M9 hedge optimisation: min-variance AND CVaR95 positions for
    a candidate exposure location, against the real contract index.
    Cached by request hash (SPEC §9.3).

    **No position constraints by default -- and that can matter a lot
    for `cvar95`.** `docs/methods/hedge.md` documents a real finding:
    the real RAINCHNNAI index has been positive in all 31 historical
    seasons, so an *unconstrained* CVaR95 minimization has no interior
    optimum and genuinely wants to short without limit -- confirmed live
    via this endpoint itself (an unconstrained request lands at
    `LotConstraints`' own 10,000-lot fallback cap with an extreme CVaR
    figure). This is the real, correct LP answer to an unconstrained
    question, not sanitized or capped by the API -- pass `constraints`
    (e.g. `max_order_lots`, `margin_budget`) for a realistic position."""
    contract_code = db.execute(
        select(Contract.contract_code).where(Contract.series_id == req.series_id)
    ).scalar_one_or_none()
    if contract_code is None:
        raise unknown_series(req.series_id)

    effective_as_of = req.as_of if req.as_of is not None else date.today()
    cache_key = _request_cache_key(req, effective_as_of)
    cached = _hedge_cache.get(cache_key)
    if cached is not None:
        return Envelope(
            data=HedgeResponseData.model_validate(cached), meta=_now_meta(as_of=effective_as_of)
        )

    spec = load_resolved_spec(db, req.series_id, contract_code)
    multiplier = req.multiplier
    if multiplier is None:
        spec_multiplier = spec.multiplier_inr_per_point
        if not isinstance(spec_multiplier, Decimal):
            raise infeasible_hedge(
                f"{req.series_id}: contract spec has no resolved multiplier -- "
                "pass `multiplier` explicitly"
            )
        multiplier = float(spec_multiplier)

    rain_grid = load_rain_grid(effective_as_of)
    official_values = official_index_values(spec, rain_grid)
    local_values = local_index_series(
        spec, rain_grid, sorted(official_values), lat=req.location_lat, lon=req.location_lon
    )
    common_years = sorted(set(local_values) & set(official_values))
    if len(common_years) < 2:
        raise infeasible_hedge(
            f"{req.series_id}: only {len(common_years)} overlapping year(s) between this location "
            "and the official index -- need at least 2 scenarios to optimise a hedge"
        )

    local_arr = np.array([local_values[y] for y in common_years])
    index_arr = np.array([official_values[y] for y in common_years])

    # Same illustrative-but-on-real-data pattern as the real M9 run
    # (docs/methods/hedge.md, .scratch/hedge_demo.py): the local CDR
    # index value, shifted non-negative, stands in for a "rain-like"
    # scale for the exposure template -- a stated simplification, not a
    # claim about the true relationship between CDR deviation and
    # absolute rainfall.
    exposure_fn = _EXPOSURE_TEMPLATES[req.exposure_template](**req.template_params)
    exposure_arr = exposure_fn(local_arr - local_arr.min())

    constraints = LotConstraints(
        max_order_lots=req.constraints.max_order_lots,
        position_limit_lots=req.constraints.position_limit_lots,
        margin_budget=req.constraints.margin_budget,
        margin_per_lot=req.constraints.margin_per_lot,
        max_notional=req.constraints.max_notional,
        notional_per_lot=req.constraints.notional_per_lot,
        long_allowed=req.constraints.long_allowed,
        short_allowed=req.constraints.short_allowed,
    )

    mv = min_variance_hedge(exposure_arr, index_arr, multiplier=multiplier, constraints=constraints)
    cvar = minimize_cvar_hedge(
        exposure_arr, index_arr, multiplier=multiplier, alpha=req.alpha, constraints=constraints
    )

    data = HedgeResponseData(
        series_id=req.series_id,
        n_years=len(common_years),
        location={"lat": req.location_lat, "lon": req.location_lon},
        exposure_template=req.exposure_template,
        multiplier=multiplier,
        min_variance=MinVarianceResult(
            h_star=mv.h_star,
            lots=mv.lots,
            h_realized=mv.h_realized,
            hedge_effectiveness=mv.hedge_effectiveness,
            residual_variance=mv.residual_variance,
            do_nothing_variance=mv.do_nothing_variance,
            basis_contribution=mv.basis_contribution,
        ),
        cvar95=Cvar95Result(
            h_star=cvar.h_star,
            lots=cvar.lots,
            h_realized=cvar.h_realized,
            cvar_95=cvar.cvar_95,
            do_nothing_cvar_95=cvar.do_nothing_cvar_95,
            var_95=cvar.var_95,
        ),
    )
    _hedge_cache[cache_key] = data.model_dump(mode="json")
    return Envelope(data=data, meta=_now_meta(as_of=effective_as_of))
