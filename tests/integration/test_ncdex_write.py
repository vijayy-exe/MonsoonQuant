import csv
from datetime import date
from pathlib import Path

from mq.db.models import MarketQuote
from mq.db.session import get_engine, session_scope
from mq.pipelines.ncdex import BHAVCOPY_SCHEMA, write_market_quotes

HEADER = list(BHAVCOPY_SCHEMA.keys())


def _row(**overrides: object) -> dict[str, object]:
    base = {
        "TradDt": "2026-10-01",
        "BizDt": "2026-10-01",
        "Sgmt": "CO",
        "Src": "NCD",
        "FinInstrmTp": "COF",
        "FinInstrmId": 123456,
        "ISIN": "",
        "TckrSymb": "RAINCHNNAI",
        "SctySrs": "",
        "XpryDt": "2026-12-31",
        "FinInstrmActlXpryDt": "2026-12-31",
        "StrkPric": 0.0,
        "OptnTp": "XX",
        "FinInstrmNm": "RAINCHNNAIDEC2026",
        "OpnPric": 1000.0,
        "HghPric": 1010.0,
        "LwPric": 995.0,
        "ClsPric": 1005.0,
        "LastPric": 1005.0,
        "PrvsClsgPric": 998.0,
        "UndrlygPric": 1005.0,
        "SttlmPric": 1005.0,
        "OpnIntrst": 120,
        "ChngInOpnIntrst": 5,
        "TtlTradgVol": 40,
        "TtlTrfVal": 2010.0,
        "TtlNbOfTxsExctd": 12,
        "SsnId": "F1",
        "NewBrdLotQty": 1,
        "Rmks": "",
        "Rsvd1": "",
        "Rsvd2": "",
        "Rsvd3": "",
        "Rsvd4": "",
    }
    base.update(overrides)
    return base


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _cleanup() -> None:
    with get_engine().connect() as conn:
        conn.exec_driver_sql("DELETE FROM market_quotes WHERE series_id = 'RAINCHNNAI-DEC26'")
        conn.commit()


def test_write_market_quotes_upserts_into_db(tmp_path: Path) -> None:
    _cleanup()
    try:
        csv_path = tmp_path / "bhav.csv"
        _write_csv(csv_path, [_row(), _row(TckrSymb="CASTOROIL")])

        n = write_market_quotes(csv_path, as_of=date(2026, 10, 1), raw_dir=tmp_path / "raw")
        assert n == 1

        with session_scope() as session:
            row = session.get(MarketQuote, ("RAINCHNNAI-DEC26", date(2026, 10, 1)))
            assert row is not None
            assert float(row.settle) == 1005.0
            assert row.volume == 40
            assert row.raw_sha256 is not None
    finally:
        _cleanup()


def test_write_market_quotes_is_idempotent_on_identical_rerun(tmp_path: Path) -> None:
    _cleanup()
    try:
        csv_path = tmp_path / "bhav.csv"
        _write_csv(csv_path, [_row()])
        write_market_quotes(csv_path, as_of=date(2026, 10, 1), raw_dir=tmp_path / "raw")
        n2 = write_market_quotes(csv_path, as_of=date(2026, 10, 1), raw_dir=tmp_path / "raw")
        assert n2 == 1  # re-ingesting is a clean upsert, not a duplicate error

        with session_scope() as session:
            count = (
                session.query(MarketQuote)
                .filter(MarketQuote.series_id == "RAINCHNNAI-DEC26")
                .count()
            )
            assert count == 1
    finally:
        _cleanup()
