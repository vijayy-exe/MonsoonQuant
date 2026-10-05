"""`/v1/ledger`, `/v1/ledger/verify` (SPEC §9.2): wraps the already-built
`mq.ledger.verify.verify_chain` directly — no new verification logic,
the API layer just exposes it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from mq.api.schemas.envelope import Envelope, Meta
from mq.db.models import PredictionLedgerRow
from mq.db.session import session_scope
from mq.ledger.verify import verify_chain

router = APIRouter(prefix="/v1/ledger", tags=["ledger"])


class ChainBreakData(BaseModel):
    row_id: int
    reason: str


class VerifyData(BaseModel):
    n_rows: int
    valid: bool
    breaks: list[ChainBreakData]


class LedgerRowData(BaseModel):
    id: int
    contract_code: str
    model_id: str
    model_version: str
    as_of_date: str
    target: str
    row_hash: str


class LedgerRowsData(BaseModel):
    rows: list[LedgerRowData]


def _now_meta(**kwargs: Any) -> Meta:
    return Meta(generated_at=datetime.now(UTC), **kwargs)


@router.get("/verify")
def ledger_verify() -> Envelope[VerifyData]:
    report = verify_chain()
    return Envelope(
        data=VerifyData(
            n_rows=report.n_rows,
            valid=report.valid,
            breaks=[ChainBreakData(row_id=b.row_id, reason=b.reason) for b in report.breaks],
        ),
        meta=_now_meta(),
    )


@router.get("")
def list_ledger(
    series: str | None = Query(default=None, alias="series"),
    model: str | None = Query(default=None, alias="model"),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
) -> Envelope[LedgerRowsData]:
    with session_scope() as session:
        stmt = select(PredictionLedgerRow)
        if series is not None:
            stmt = stmt.where(PredictionLedgerRow.contract_code == series)
        if model is not None:
            stmt = stmt.where(PredictionLedgerRow.model_id == model)
        if date_from is not None:
            stmt = stmt.where(PredictionLedgerRow.as_of_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(PredictionLedgerRow.as_of_date <= date_to)
        rows = session.execute(stmt.order_by(PredictionLedgerRow.id.asc())).scalars().all()
        data = LedgerRowsData(
            rows=[
                LedgerRowData(
                    id=r.id,
                    contract_code=r.contract_code,
                    model_id=r.model_id,
                    model_version=r.model_version,
                    as_of_date=r.as_of_date.isoformat(),
                    target=r.target,
                    row_hash=r.row_hash,
                )
                for r in rows
            ]
        )
    return Envelope(data=data, meta=_now_meta())
