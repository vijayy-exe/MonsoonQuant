from datetime import date
from pathlib import Path

from mq.db.models import Contract, ContractSpecRow
from mq.db.session import get_engine, session_scope
from mq.specs.loader import load_contract_spec
from mq.specs.registry import register_contract_spec, register_listed_series

RAINCHNNAI_SPEC = Path("specs/contracts/RAINCHNNAI/2026-08-31.yaml")


def _cleanup() -> None:
    with get_engine().connect() as conn:
        conn.exec_driver_sql(
            "DELETE FROM contracts WHERE contract_code = 'RAINCHNNAI'; "
            "DELETE FROM contract_specs WHERE contract_code = 'RAINCHNNAI';"
        )
        conn.commit()


def test_register_contract_spec_and_listed_series() -> None:
    _cleanup()
    try:
        spec = load_contract_spec(RAINCHNNAI_SPEC)
        register_contract_spec(spec)

        with session_scope() as session:
            row = session.get(ContractSpecRow, ("RAINCHNNAI", "2026-08-31"))
            assert row is not None
            assert row.yaml["contract_code"] == "RAINCHNNAI"
            assert "ncdex_spec_rainchnnai_2026" in row.source_ids

        rows = register_listed_series(
            spec,
            expiry_months=[(2026, 9), (2026, 10), (2026, 11), (2026, 12)],
            as_of=date(2026, 10, 4),
        )
        assert {r.series_id for r in rows} == {
            "RAINCHNNAI-SEP26",
            "RAINCHNNAI-OCT26",
            "RAINCHNNAI-NOV26",
            "RAINCHNNAI-DEC26",
        }
        by_id = {r.series_id: r for r in rows}
        # Sep 2026 has already settled as of Oct 4; Oct/Nov/Dec have not.
        assert by_id["RAINCHNNAI-SEP26"].status == "expired"
        assert by_id["RAINCHNNAI-OCT26"].status == "active"
        assert by_id["RAINCHNNAI-DEC26"].period_start == date(2026, 9, 1)
        assert by_id["RAINCHNNAI-DEC26"].period_end == date(2026, 12, 31)

        with session_scope() as session:
            count = session.query(Contract).filter(Contract.contract_code == "RAINCHNNAI").count()
            assert count == 4
    finally:
        _cleanup()
