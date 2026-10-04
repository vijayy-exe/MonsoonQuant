"""Verifies the prediction_ledger hash chain (SPEC §2.1) — `mq ledger verify`.

Recomputes payload_sha256 and row_hash for every row in id order and checks
them against what's stored, and checks each row's prev_hash against the
previous row's actual row_hash. Any mismatch means the chain has been
tampered with or corrupted."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from mq.db.models import PredictionLedgerRow
from mq.db.session import session_scope
from mq.ledger.hashing import GENESIS_HASH, payload_hash, row_hash


@dataclass
class ChainBreak:
    row_id: int
    reason: str


@dataclass
class VerifyReport:
    n_rows: int
    valid: bool
    breaks: list[ChainBreak] = field(default_factory=list)


def _row_core_fields(row: PredictionLedgerRow) -> dict[str, Any]:
    return {
        "issued_at": row.issued_at,
        "as_of_date": row.as_of_date,
        "contract_code": row.contract_code,
        "model_id": row.model_id,
        "model_version": row.model_version,
        "data_version": row.data_version,
        "target": row.target,
        "quantiles": row.quantiles,
        "fair_value": row.fair_value,
        "fair_value_lo90": row.fair_value_lo90,
        "fair_value_hi90": row.fair_value_hi90,
    }


def verify_chain() -> VerifyReport:
    with session_scope() as session:
        rows = (
            session.execute(select(PredictionLedgerRow).order_by(PredictionLedgerRow.id.asc()))
            .scalars()
            .all()
        )

        breaks: list[ChainBreak] = []
        expected_prev = GENESIS_HASH
        for row in rows:
            expected_payload = payload_hash(_row_core_fields(row))
            if expected_payload != row.payload_sha256:
                breaks.append(ChainBreak(row.id, "payload_sha256 does not match row content"))

            if row.prev_hash != expected_prev:
                breaks.append(
                    ChainBreak(row.id, f"prev_hash mismatch (expected {expected_prev[:12]}...)")
                )

            expected_row_hash = row_hash(row.prev_hash, row.payload_sha256)
            if expected_row_hash != row.row_hash:
                breaks.append(ChainBreak(row.id, "row_hash does not match prev_hash+payload"))

            expected_prev = row.row_hash

        return VerifyReport(n_rows=len(rows), valid=len(breaks) == 0, breaks=breaks)
