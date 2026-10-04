from datetime import date

import polars as pl

from mq.pipelines.dq import (
    dq01_missing_dates,
    dq02_duplicate_keys,
    dq03_value_range,
    dq04_schema_drift,
    gate,
)


def test_dq01_passes_on_complete_range() -> None:
    df = pl.DataFrame({"date": [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]})
    result = dq01_missing_dates(
        df,
        date_col="date",
        dataset="test",
        expected_start=date(2026, 1, 1),
        expected_end=date(2026, 1, 3),
    )
    assert result.status == "pass"


def test_dq01_fails_on_missing_dates() -> None:
    df = pl.DataFrame({"date": [date(2026, 1, 1), date(2026, 1, 3)]})
    result = dq01_missing_dates(
        df,
        date_col="date",
        dataset="test",
        expected_start=date(2026, 1, 1),
        expected_end=date(2026, 1, 3),
    )
    assert result.status == "fail"
    assert result.details["missing_count"] == 1
    assert result.details["missing_dates"] == ["2026-01-02"]


def test_dq02_fails_on_duplicate_keys() -> None:
    df = pl.DataFrame({"date": [date(2026, 1, 1), date(2026, 1, 1)], "lat": [1.0, 1.0]})
    result = dq02_duplicate_keys(df, key_cols=["date", "lat"], dataset="test")
    assert result.status == "fail"
    assert result.details["duplicate_count"] == 1


def test_dq02_passes_on_unique_keys() -> None:
    df = pl.DataFrame({"date": [date(2026, 1, 1), date(2026, 1, 2)], "lat": [1.0, 1.0]})
    result = dq02_duplicate_keys(df, key_cols=["date", "lat"], dataset="test")
    assert result.status == "pass"


def test_dq03_fails_on_out_of_range_value() -> None:
    df = pl.DataFrame({"rain_mm": [0.0, 50.0, 1500.0]})
    result = dq03_value_range(df, value_col="rain_mm", dataset="test", lo=0.0, hi=1000.0)
    assert result.status == "fail"
    assert result.details["out_of_range_count"] == 1


def test_dq03_fails_on_negative_value() -> None:
    df = pl.DataFrame({"rain_mm": [-5.0, 50.0]})
    result = dq03_value_range(df, value_col="rain_mm", dataset="test", lo=0.0, hi=1000.0)
    assert result.status == "fail"


def test_dq04_fails_on_missing_column() -> None:
    df = pl.DataFrame({"date": [date(2026, 1, 1)]})
    result = dq04_schema_drift(
        df, expected_schema={"date": pl.Date(), "value": pl.Float64()}, dataset="test"
    )
    assert result.status == "fail"
    assert result.details["missing_columns"] == ["value"]


def test_dq04_fails_on_type_mismatch() -> None:
    df = pl.DataFrame({"value": ["not a float"]})
    result = dq04_schema_drift(df, expected_schema={"value": pl.Float64()}, dataset="test")
    assert result.status == "fail"
    assert "value" in result.details["type_mismatches"]


def test_dq04_passes_on_matching_schema() -> None:
    df = pl.DataFrame({"date": [date(2026, 1, 1)], "value": [1.0]})
    result = dq04_schema_drift(
        df, expected_schema={"date": pl.Date(), "value": pl.Float64()}, dataset="test"
    )
    assert result.status == "pass"


def test_gate_blocks_on_any_failure() -> None:
    df = pl.DataFrame({"rain_mm": [-5.0]})
    ok = dq03_value_range(df, value_col="rain_mm", dataset="test", lo=-10.0, hi=10.0)
    bad = dq03_value_range(df, value_col="rain_mm", dataset="test", lo=0.0, hi=10.0)
    assert gate([ok]) is True
    assert gate([ok, bad]) is False
