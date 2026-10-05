"""`/v1/series/{id}/valuation` and `/v1/series/{id}/valuations/compare`
(SPEC §9.2): the real `valuations` table rows M4's `write_burn_valuation`/
`write_distribution_valuation` wrote — no synthetic placeholders.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from mq.api.deps import get_db
from mq.api.errors import unknown_series
from mq.api.schemas.envelope import Envelope, Meta
from mq.db.models import Contract, Valuation

router = APIRouter(prefix="/v1/series", tags=["series"])


class ValuationData(BaseModel):
    series_id: str
    as_of_date: str
    method: str
    measure: str
    fair_value: float | None
    lo90: float | None
    hi90: float | None
    n_paths: int | None


class ValuationsCompareData(BaseModel):
    series_id: str
    as_of_date: str
    by_method: dict[str, ValuationData]


def _now_meta(**kwargs: Any) -> Meta:
    return Meta(generated_at=datetime.now(UTC), **kwargs)


def _assert_series_exists(db: Session, series_id: str) -> None:
    exists = db.execute(select(Contract.series_id).where(Contract.series_id == series_id)).first()
    if exists is None:
        raise unknown_series(series_id)


def _to_valuation_data(row: Valuation) -> ValuationData:
    return ValuationData(
        series_id=row.series_id,
        as_of_date=row.as_of_date.isoformat(),
        method=row.method,
        measure=row.measure,
        fair_value=float(row.fair_value) if row.fair_value is not None else None,
        lo90=float(row.lo90) if row.lo90 is not None else None,
        hi90=float(row.hi90) if row.hi90 is not None else None,
        n_paths=row.n_paths,
    )


@router.get("/{series_id}/valuation")
def get_valuation(
    series_id: str,
    as_of: date | None = Query(default=None),
    method: str = Query(default="burn"),
    measure: str = Query(default="P"),
    db: Session = Depends(get_db),
) -> Envelope[ValuationData]:
    _assert_series_exists(db, series_id)
    stmt = select(Valuation).where(
        Valuation.series_id == series_id, Valuation.method == method, Valuation.measure == measure
    )
    stmt = (
        stmt.where(Valuation.as_of_date == as_of)
        if as_of is not None
        else stmt.order_by(Valuation.as_of_date.desc())
    )
    row = db.execute(stmt.limit(1)).scalars().first()
    if row is None:
        raise unknown_series(f"{series_id} has no {method}/{measure} valuation")
    return Envelope(
        data=_to_valuation_data(row),
        meta=_now_meta(as_of=row.as_of_date),
    )


@router.get("/{series_id}/valuations/compare")
def compare_valuations(
    series_id: str, as_of: date | None = Query(default=None), db: Session = Depends(get_db)
) -> Envelope[ValuationsCompareData]:
    """SPEC's "all 4 methods side-by-side" — currently returns whichever
    methods/measures actually have real rows written for this series
    (burn and dist, per M4; conditioned/mpr rungs not yet written to
    this table — see docs/STATUS.md), not a fabricated 4-method set.

    Each method's own MOST RECENT row, not "whatever was written on the
    literal same calendar day" — real data showed burn and dist were
    written a day apart for RAINCHNNAI (M4 ran them in separate passes),
    so a same-day join would have silently dropped one method entirely
    whenever `as_of` isn't given. `as_of`, when given, bounds every
    method's own latest row to "at or before that date" rather than
    requiring an exact match."""
    _assert_series_exists(db, series_id)
    stmt = select(Valuation).where(Valuation.series_id == series_id)
    if as_of is not None:
        stmt = stmt.where(Valuation.as_of_date <= as_of)
    rows = db.execute(stmt.order_by(Valuation.as_of_date.desc())).scalars().all()
    if not rows:
        raise unknown_series(f"{series_id} has no valuations")

    by_method: dict[str, ValuationData] = {}
    for r in rows:
        key = f"{r.method}/{r.measure}"
        if key not in by_method:  # rows are already newest-first -> first hit per key is the latest
            by_method[key] = _to_valuation_data(r)

    latest_as_of = max(v.as_of_date for v in by_method.values())
    return Envelope(
        data=ValuationsCompareData(
            series_id=series_id, as_of_date=latest_as_of, by_method=by_method
        ),
        meta=_now_meta(as_of=date.fromisoformat(latest_as_of)),
    )
