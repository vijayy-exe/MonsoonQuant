from datetime import date

import polars as pl

from mq.pipelines.dq import (
    dq01_missing_dates,
    dq02_duplicate_keys,
    dq03_value_range,
    dq04_schema_drift,
    dq08_climate_index_revision,
    dq09_proxy_index_jump,
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


def test_dq08_passes_when_no_prior_data_exists() -> None:
    incoming = pl.DataFrame(
        {
            "index": ["oni"],
            "date": [date(2026, 8, 15)],
            "value": [0.5],
            "release_date": [date(2026, 10, 4)],
        }
    )
    result = dq08_climate_index_revision(incoming, pl.DataFrame(), dataset="test")
    assert result.status == "pass"
    assert result.details == {}


def test_dq08_reports_info_on_a_real_revision() -> None:
    existing = pl.DataFrame(
        {
            "index": ["oni"],
            "date": [date(2026, 8, 15)],
            "value": [0.5],
            "release_date": [date(2026, 9, 1)],
        }
    )
    incoming = pl.DataFrame(
        {
            "index": ["oni"],
            "date": [date(2026, 8, 15)],
            "value": [0.6],
            "release_date": [date(2026, 10, 4)],
        }
    )
    result = dq08_climate_index_revision(incoming, existing, dataset="test")
    assert result.status == "info"
    assert result.details["revised_count"] == 1
    assert result.details["revisions"][0]["previous_value"] == 0.5
    assert result.details["revisions"][0]["new_value"] == 0.6


def test_dq08_passes_when_value_unchanged() -> None:
    existing = pl.DataFrame(
        {
            "index": ["oni"],
            "date": [date(2026, 8, 15)],
            "value": [0.5],
            "release_date": [date(2026, 9, 1)],
        }
    )
    incoming = pl.DataFrame(
        {
            "index": ["oni"],
            "date": [date(2026, 8, 15)],
            "value": [0.5],
            "release_date": [date(2026, 10, 4)],
        }
    )
    result = dq08_climate_index_revision(incoming, existing, dataset="test")
    assert result.status == "pass"
    assert result.details["revised_count"] == 0


def test_dq09_passes_on_normal_day_to_day_changes() -> None:
    df = pl.DataFrame({"deviation_mm": [1.0, -1.0, 2.0, -2.0, 1.5, -1.5, 0.5]})
    result = dq09_proxy_index_jump(df, value_col="deviation_mm", dataset="test")
    assert result.status == "pass"


def test_dq09_warns_on_a_real_outlier_jump() -> None:
    # Many small, everyday deviations keep the sample sd small, so one
    # genuinely extreme day (500mm) clears 3 sigma without the outlier
    # itself inflating the threshold past its own value.
    baseline = [1.0, -1.0, 2.0, -2.0, 1.5, -1.5, 0.5, -0.5] * 10
    df = pl.DataFrame({"deviation_mm": [*baseline, 500.0]})
    result = dq09_proxy_index_jump(df, value_col="deviation_mm", dataset="test")
    assert result.status == "warn"
    assert result.details["breach_count"] == 1


def test_dq09_passes_with_fewer_than_two_observations() -> None:
    df = pl.DataFrame({"deviation_mm": [500.0]})
    result = dq09_proxy_index_jump(df, value_col="deviation_mm", dataset="test")
    assert result.status == "pass"


def test_gate_blocks_on_any_failure() -> None:
    df = pl.DataFrame({"rain_mm": [-5.0]})
    ok = dq03_value_range(df, value_col="rain_mm", dataset="test", lo=-10.0, hi=10.0)
    bad = dq03_value_range(df, value_col="rain_mm", dataset="test", lo=0.0, hi=10.0)
    assert gate([ok]) is True
    assert gate([ok, bad]) is False
