"""Prediction ledger writer (SPEC §2.1): append-only, hash-chained.

Idempotent per (contract_code, as_of_date, model_id, model_version) — a
re-run of the same day's forecast with the same model is a no-op, per
SPEC §8.1: "re-running a day produces identical outputs (except issued_at
ledger rows, which are skipped if the same (as_of, model_id, model_version)
exists)."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mq.db.models import PredictionLedgerRow
from mq.db.session import session_scope
from mq.ledger.hashing import GENESIS_HASH, canonical_json, payload_hash, row_hash


@dataclass(frozen=True)
class ForecastToWrite:
    contract_code: str
    model_id: str
    model_version: str
    data_version: str
    as_of_date: date
    target: str  # 'final_index' | 'remaining_rain_mm'
    quantiles: dict[str, float]
    fair_value: Decimal | None = None
    fair_value_lo90: Decimal | None = None
    fair_value_hi90: Decimal | None = None


def _core_fields(forecast: ForecastToWrite, issued_at: datetime) -> dict[str, Any]:
    return {
        "issued_at": issued_at,
        "as_of_date": forecast.as_of_date,
        "contract_code": forecast.contract_code,
        "model_id": forecast.model_id,
        "model_version": forecast.model_version,
        "data_version": forecast.data_version,
        "target": forecast.target,
        "quantiles": forecast.quantiles,
        "fair_value": forecast.fair_value,
        "fair_value_lo90": forecast.fair_value_lo90,
        "fair_value_hi90": forecast.fair_value_hi90,
    }


def _latest_row_hash(session: Session) -> str:
    stmt = select(PredictionLedgerRow.row_hash).order_by(PredictionLedgerRow.id.desc()).limit(1)
    latest = session.execute(stmt).scalar_one_or_none()
    return latest if latest is not None else GENESIS_HASH


def write_forecast(forecast: ForecastToWrite) -> PredictionLedgerRow | None:
    """Write one forecast to the ledger. Returns the new row, or None if an
    identical (contract_code, as_of_date, model_id, model_version) row
    already exists (idempotent skip — SPEC §8.1)."""
    with session_scope() as session:
        existing = session.execute(
            select(PredictionLedgerRow).where(
                PredictionLedgerRow.contract_code == forecast.contract_code,
                PredictionLedgerRow.as_of_date == forecast.as_of_date,
                PredictionLedgerRow.model_id == forecast.model_id,
                PredictionLedgerRow.model_version == forecast.model_version,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return None

        issued_at = datetime.now(UTC)
        core = _core_fields(forecast, issued_at)
        payload_sha256 = payload_hash(core)
        prev_hash = _latest_row_hash(session)
        new_row_hash = row_hash(prev_hash, payload_sha256)

        row = PredictionLedgerRow(
            issued_at=issued_at,
            as_of_date=forecast.as_of_date,
            contract_code=forecast.contract_code,
            model_id=forecast.model_id,
            model_version=forecast.model_version,
            data_version=forecast.data_version,
            target=forecast.target,
            quantiles=forecast.quantiles,
            fair_value=forecast.fair_value,
            fair_value_lo90=forecast.fair_value_lo90,
            fair_value_hi90=forecast.fair_value_hi90,
            payload_sha256=payload_sha256,
            prev_hash=prev_hash,
            row_hash=new_row_hash,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        # Detach with attributes already loaded so the caller can read them
        # after this session commits and closes (session_scope's teardown
        # would otherwise expire — and then be unable to reload — the row).
        session.expunge(row)
        return row


__all__ = ["ForecastToWrite", "canonical_json", "write_forecast"]
