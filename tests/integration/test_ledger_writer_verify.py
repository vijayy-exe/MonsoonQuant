from datetime import date

from mq.db.models import PredictionLedgerRow
from mq.db.session import get_engine, session_scope
from mq.ledger.verify import verify_chain
from mq.ledger.writer import ForecastToWrite, write_forecast

TEST_CONTRACT = "TEST_LEDGER_CHAIN"


def _cleanup() -> None:
    with get_engine().connect() as conn:
        conn.exec_driver_sql(
            "SET session_replication_role = replica; "
            f"DELETE FROM prediction_ledger WHERE contract_code = '{TEST_CONTRACT}'; "
            "SET session_replication_role = DEFAULT;"
        )
        conn.commit()


def test_write_forecast_links_to_prior_row_and_is_idempotent() -> None:
    _cleanup()
    try:
        f1 = ForecastToWrite(
            contract_code=TEST_CONTRACT,
            model_id="test_model",
            model_version="0.0.1",
            data_version="test",
            as_of_date=date(2026, 10, 1),
            target="remaining_rain_mm",
            quantiles={"0.5": 100.0},
        )
        row1 = write_forecast(f1)
        assert row1 is not None

        f2 = ForecastToWrite(
            contract_code=TEST_CONTRACT,
            model_id="test_model",
            model_version="0.0.1",
            data_version="test",
            as_of_date=date(2026, 10, 2),
            target="remaining_rain_mm",
            quantiles={"0.5": 90.0},
        )
        row2 = write_forecast(f2)
        assert row2 is not None
        assert row2.prev_hash == row1.row_hash

        # Idempotent: identical (contract, as_of, model_id, model_version) is a no-op.
        repeat = write_forecast(f1)
        assert repeat is None

        with session_scope() as session:
            count = (
                session.query(PredictionLedgerRow)
                .filter(PredictionLedgerRow.contract_code == TEST_CONTRACT)
                .count()
            )
            assert count == 2
    finally:
        _cleanup()


def test_verify_chain_passes_on_untampered_ledger() -> None:
    report = verify_chain()
    assert report.valid
    assert report.breaks == []


def test_verify_chain_detects_a_tampered_row() -> None:
    _cleanup()
    try:
        f1 = ForecastToWrite(
            contract_code=TEST_CONTRACT,
            model_id="test_model",
            model_version="0.0.1",
            data_version="test",
            as_of_date=date(2026, 10, 1),
            target="remaining_rain_mm",
            quantiles={"0.5": 100.0},
        )
        row1 = write_forecast(f1)
        assert row1 is not None

        # Insert a row with a deliberately wrong prev_hash — simulates a
        # tampered/forged ledger entry. INSERT (unlike UPDATE/DELETE) isn't
        # blocked by the immutability trigger, so this is possible, and is
        # exactly the attack verify_chain must catch.
        fake_payload_hash = "0" * 64
        fake_row_hash = "1" * 64
        with get_engine().connect() as conn:
            conn.exec_driver_sql(
                f"""
                INSERT INTO prediction_ledger
                (issued_at, as_of_date, contract_code, model_id, model_version,
                 data_version, target, quantiles, payload_sha256, prev_hash, row_hash)
                VALUES (now(), '2026-10-02', '{TEST_CONTRACT}', 'test_model', '0.0.2',
                        'test', 'remaining_rain_mm', '{{"0.5": 1}}'::jsonb,
                        '{fake_payload_hash}', 'not-the-real-prev-hash', '{fake_row_hash}')
                """
            )
            conn.commit()

        report = verify_chain()
        assert not report.valid
        tampered_ids = {b.row_id for b in report.breaks}
        with session_scope() as session:
            tampered_row = (
                session.query(PredictionLedgerRow)
                .filter(PredictionLedgerRow.model_version == "0.0.2")
                .one()
            )
            assert tampered_row.id in tampered_ids
    finally:
        _cleanup()
