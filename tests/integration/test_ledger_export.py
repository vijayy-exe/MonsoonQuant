import json
from datetime import date
from pathlib import Path

from mq.db.session import get_engine
from mq.ledger.export import export_day
from mq.ledger.writer import ForecastToWrite, write_forecast

TEST_CONTRACT = "TEST_LEDGER_EXPORT"


def _cleanup() -> None:
    with get_engine().connect() as conn:
        conn.exec_driver_sql(
            "SET session_replication_role = replica; "
            f"DELETE FROM prediction_ledger WHERE contract_code = '{TEST_CONTRACT}'; "
            "SET session_replication_role = DEFAULT;"
        )
        conn.commit()


def test_export_day_writes_jsonl_for_rows_issued_that_day(tmp_path: Path) -> None:
    _cleanup()
    try:
        row = write_forecast(
            ForecastToWrite(
                contract_code=TEST_CONTRACT,
                model_id="test_model",
                model_version="0.0.1",
                data_version="test",
                as_of_date=date(2026, 10, 4),
                target="remaining_rain_mm",
                quantiles={"0.5": 42.0},
            )
        )
        assert row is not None
        today = row.issued_at.date()

        out_path = export_day(today, export_dir=tmp_path)
        assert out_path is not None
        assert (
            out_path
            == tmp_path / f"{today.year:04d}" / f"{today.month:02d}" / f"{today.day:02d}.jsonl"
        )

        lines = out_path.read_text().splitlines()
        matching = [
            json.loads(line) for line in lines if json.loads(line)["contract_code"] == TEST_CONTRACT
        ]
        assert len(matching) == 1
        assert matching[0]["row_hash"] == row.row_hash
        assert matching[0]["quantiles"] == {"0.5": 42.0}
    finally:
        _cleanup()


def test_export_day_returns_none_when_no_rows(tmp_path: Path) -> None:
    out_path = export_day(date(1999, 1, 1), export_dir=tmp_path)
    assert out_path is None
