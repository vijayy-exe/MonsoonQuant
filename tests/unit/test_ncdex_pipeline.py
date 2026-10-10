"""Tests against a synthetic UDiFF bhavcopy CSV, built to the documented
34-column schema (specs/sources/ncdex_udiff_bhavcopy_format_2024.yaml) —
no live fetch (ncdex.com's bhavcopy API is bot-gated, see docs/DECISIONS.md)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from mq.pipelines.ncdex import (
    BHAVCOPY_SCHEMA,
    parse_bhavcopy,
    run_market_quotes_dq,
    to_market_quotes,
)

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
        "FininstrmActlXpryDt": "2026-12-31",
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
    import csv

    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_parse_bhavcopy_reads_all_documented_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "bhav.csv"
    _write_csv(csv_path, [_row(), _row(TckrSymb="CASTOROIL", FinInstrmNm="CASTOROIL19APR2024")])
    df = parse_bhavcopy(csv_path)
    assert df.height == 2
    assert set(df.columns) == set(BHAVCOPY_SCHEMA.keys())


def test_to_market_quotes_filters_to_known_contracts_and_derives_series_id(tmp_path: Path) -> None:
    csv_path = tmp_path / "bhav.csv"
    _write_csv(
        csv_path,
        [
            _row(TckrSymb="RAINCHNNAI", XpryDt="2026-12-31", SttlmPric=1005.0),
            _row(TckrSymb="RAINMUMBAI", XpryDt="2026-09-30", SttlmPric=2200.5),
            _row(TckrSymb="CASTOROIL", FinInstrmNm="CASTOROIL19APR2024"),  # must be dropped
        ],
    )
    raw = parse_bhavcopy(csv_path)
    quotes = to_market_quotes(raw)
    assert quotes.height == 2
    assert set(quotes["series_id"].to_list()) == {"RAINCHNNAI-DEC26", "RAINMUMBAI-SEP26"}
    assert quotes.filter(quotes["series_id"] == "RAINCHNNAI-DEC26")["settle"].item() == 1005.0


def test_to_market_quotes_empty_when_no_known_contracts(tmp_path: Path) -> None:
    csv_path = tmp_path / "bhav.csv"
    _write_csv(csv_path, [_row(TckrSymb="CASTOROIL", FinInstrmNm="CASTOROIL19APR2024")])
    raw = parse_bhavcopy(csv_path)
    quotes = to_market_quotes(raw)
    assert quotes.height == 0
    assert "series_id" in quotes.columns


def test_dq_flags_settle_breaching_the_daily_price_band(tmp_path: Path) -> None:
    csv_path = tmp_path / "bhav.csv"
    _write_csv(
        csv_path,
        [
            _row(TradDt="2026-10-01", SttlmPric=1000.0, PrvsClsgPric=1000.0),
            # +20% day-on-day move, well outside the 6% initial slab
            _row(TradDt="2026-10-02", SttlmPric=1200.0, PrvsClsgPric=1000.0),
        ],
    )
    raw = parse_bhavcopy(csv_path)
    quotes = to_market_quotes(raw)
    results = run_market_quotes_dq(quotes, raw, as_of=date(2026, 10, 2), dataset="test")
    dq10 = next(r for r in results if r.check_id == "DQ10")
    assert dq10.status == "warn"
    assert dq10.details["breach_count"] == 1


def test_dq_flags_unknown_contract_code(tmp_path: Path) -> None:
    csv_path = tmp_path / "bhav.csv"
    _write_csv(csv_path, [_row(TckrSymb="RAINCHNNAI"), _row(TckrSymb="CASTOROIL")])
    raw = parse_bhavcopy(csv_path)
    quotes = to_market_quotes(raw)
    results = run_market_quotes_dq(quotes, raw, as_of=date(2026, 10, 1), dataset="test")
    dq06 = next(r for r in results if r.check_id == "DQ06")
    assert dq06.status == "warn"
    assert "CASTOROIL" in dq06.details["unknown_codes"]


def test_dq_flags_stale_market_data(tmp_path: Path) -> None:
    csv_path = tmp_path / "bhav.csv"
    _write_csv(csv_path, [_row(TradDt="2026-09-01")])
    raw = parse_bhavcopy(csv_path)
    quotes = to_market_quotes(raw)
    results = run_market_quotes_dq(quotes, raw, as_of=date(2026, 10, 4), dataset="test")
    dq05 = next(r for r in results if r.check_id == "DQ05")
    assert dq05.status == "warn"
    assert dq05.details["staleness_days"] == 33
