from datetime import date

from mq.db.models import IndexValue
from mq.db.session import get_engine, session_scope
from mq.index.engine import IndexPath
from mq.index.writer import write_index_values

TEST_SERIES = ["TESTCDR-SEP26", "TESTCDR-OCT26"]


def _path() -> IndexPath:
    return IndexPath(
        contract_code="TESTCDR",
        as_of=date(2026, 9, 2),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 12, 31),
        season_lpa_anchor=100.0,
        dates=[date(2026, 9, 1), date(2026, 9, 2)],
        daily_rainfall_mm=[1.0, 2.0],
        daily_lpa_mm=[1.0, 1.0],
        daily_deviation_mm=[0.0, 1.0],
        spot=[100.0, 101.0],
    )


def _cleanup() -> None:
    with get_engine().connect() as conn:
        conn.exec_driver_sql(
            "DELETE FROM index_values WHERE series_id IN ('TESTCDR-SEP26', 'TESTCDR-OCT26')"
        )
        conn.commit()


def test_write_index_values_writes_one_row_per_series_per_date() -> None:
    _cleanup()
    try:
        rows = write_index_values(_path(), series_ids=TEST_SERIES, data_version="test")
        assert len(rows) == 4  # 2 series x 2 dates

        with session_scope() as session:
            row = session.get(IndexValue, ("TESTCDR-SEP26", date(2026, 9, 2), date(2026, 9, 2)))
            assert row is not None
            assert float(row.proxy_value) == 101.0
            assert row.official_value is None
            assert row.data_version == "test"
    finally:
        _cleanup()
