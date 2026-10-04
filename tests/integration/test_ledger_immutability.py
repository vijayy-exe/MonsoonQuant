"""Proves the prediction_ledger append-only trigger (SPEC §2.1) actually
blocks mutation at the database level. Requires the local Postgres from
`docker compose up -d postgres` (MQ_DATABASE_URL)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from mq.db.models import PredictionLedgerRow
from mq.db.session import get_engine, session_scope


@pytest.fixture
def ledger_row_id() -> int:
    with session_scope() as session:
        row = PredictionLedgerRow(
            issued_at=datetime.now(UTC),
            as_of_date=date(2026, 10, 4),
            contract_code="RAINCHNNAI",
            model_id="test_immutability",
            model_version="0.0.0",
            data_version="test",
            target="final_index",
            quantiles={"0.5": 100.0},
            payload_sha256="0" * 64,
            prev_hash="0" * 64,
            row_hash="test-" + datetime.now(UTC).isoformat(),
        )
        session.add(row)
        session.flush()
        row_id = row.id
    yield row_id
    # Cleanup bypasses the ORM trigger guard by deleting via raw SQL as the
    # test teardown would otherwise be blocked by the very trigger we test.
    with get_engine().connect() as conn:
        conn.exec_driver_sql(
            "SET session_replication_role = replica; "
            f"DELETE FROM prediction_ledger WHERE id = {row_id}; "
            "SET session_replication_role = DEFAULT;"
        )
        conn.commit()


def test_update_is_blocked(ledger_row_id: int) -> None:
    with pytest.raises(ProgrammingError, match="append-only"), Session(get_engine()) as session:
        row = session.get(PredictionLedgerRow, ledger_row_id)
        assert row is not None
        row.fair_value = 999
        session.commit()


def test_delete_is_blocked(ledger_row_id: int) -> None:
    with pytest.raises(ProgrammingError, match="append-only"), Session(get_engine()) as session:
        row = session.get(PredictionLedgerRow, ledger_row_id)
        assert row is not None
        session.delete(row)
        session.commit()
