"""`/v1/contracts`, `/v1/contracts/{code}/spec` (SPEC §9.2): the real
contract/series registry M1's `mq.specs.registry` wrote to the DB —
no synthetic placeholders, this is the real NCDEX contract calendar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from mq.api.deps import get_db
from mq.api.errors import unknown_series
from mq.api.schemas.envelope import Envelope, Meta
from mq.db.models import Contract, ContractSpecRow

router = APIRouter(prefix="/v1/contracts", tags=["contracts"])


class ListedSeriesData(BaseModel):
    series_id: str
    contract_code: str | None
    spec_version: str | None
    period_start: str | None
    period_end: str | None
    expiry: str | None
    status: str | None


class ContractsListData(BaseModel):
    series: list[ListedSeriesData]


class ContractSpecData(BaseModel):
    contract_code: str
    spec_version: str
    yaml: dict[str, Any]
    source_ids: list[str]


def _now_meta(**kwargs: Any) -> Meta:
    return Meta(generated_at=datetime.now(UTC), **kwargs)


@router.get("")
def list_contracts(db: Session = Depends(get_db)) -> Envelope[ContractsListData]:
    rows = db.execute(select(Contract).order_by(Contract.series_id)).scalars().all()
    series = [
        ListedSeriesData(
            series_id=r.series_id,
            contract_code=r.contract_code,
            spec_version=r.spec_version,
            period_start=r.period_start.isoformat() if r.period_start else None,
            period_end=r.period_end.isoformat() if r.period_end else None,
            expiry=r.expiry.isoformat() if r.expiry else None,
            status=r.status,
        )
        for r in rows
    ]
    return Envelope(data=ContractsListData(series=series), meta=_now_meta())


@router.get("/{code}/spec")
def get_contract_spec(code: str, db: Session = Depends(get_db)) -> Envelope[ContractSpecData]:
    row = db.execute(
        select(ContractSpecRow)
        .where(ContractSpecRow.contract_code == code)
        .order_by(ContractSpecRow.spec_version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise unknown_series(code)
    return Envelope(
        data=ContractSpecData(
            contract_code=row.contract_code,
            spec_version=row.spec_version,
            yaml=row.yaml,
            source_ids=row.source_ids,
        ),
        meta=_now_meta(spec_version=row.spec_version),
    )
