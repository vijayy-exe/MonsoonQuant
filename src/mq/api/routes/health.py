"""`/v1/health`, `/v1/health/data` (SPEC §9.2): liveness, and data
freshness per source — checks the DB directly rather than caching a
separate health-check table, so a stale answer can never outlive the
data it describes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mq.api.deps import get_db
from mq.api.schemas.envelope import Envelope, Meta
from mq.db.models import IndexValue, MarketQuote, PredictionLedgerRow

router = APIRouter(prefix="/v1/health", tags=["health"])


class HealthData(BaseModel):
    status: str = "ok"


class SourceFreshness(BaseModel):
    source: str
    latest_date: str | None
    n_rows: int


class DataFreshnessData(BaseModel):
    sources: list[SourceFreshness]


def _now_meta() -> Meta:
    return Meta(generated_at=datetime.now(UTC))


@router.get("")
def health() -> Envelope[HealthData]:
    return Envelope(data=HealthData(), meta=_now_meta())


@router.get("/data")
def health_data(db: Session = Depends(get_db)) -> Envelope[DataFreshnessData]:
    sources = []
    for name, model, date_col in [
        ("index_values", IndexValue, IndexValue.obs_date),
        ("market_quotes", MarketQuote, MarketQuote.trade_date),
        ("prediction_ledger", PredictionLedgerRow, PredictionLedgerRow.as_of_date),
    ]:
        latest_stmt = select(date_col).order_by(date_col.desc()).limit(1)
        latest = db.execute(latest_stmt).scalar_one_or_none()
        count = db.execute(select(func.count()).select_from(model)).scalar_one()
        sources.append(
            SourceFreshness(
                source=name,
                latest_date=latest.isoformat() if latest is not None else None,
                n_rows=count,
            )
        )
    return Envelope(data=DataFreshnessData(sources=sources), meta=_now_meta())
