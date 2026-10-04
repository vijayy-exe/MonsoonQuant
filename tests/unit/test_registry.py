from datetime import date

from mq.specs.registry import ListedSeries, series_id_for


def test_series_id_format() -> None:
    assert series_id_for("RAINCHNNAI", 2026, 12) == "RAINCHNNAI-DEC26"
    assert series_id_for("RAINMUMBAI", 2026, 9) == "RAINMUMBAI-SEP26"


def test_last_trading_day_skips_weekend() -> None:
    # Dec 31, 2026 is a Thursday -> last trading day is Dec 31 itself.
    series = ListedSeries(series_id="X", expiry_year=2026, expiry_month=12)
    assert series.last_trading_day == date(2026, 12, 31)
    assert series.due_day == date(2027, 1, 1)


def test_last_trading_day_rolls_back_from_weekend() -> None:
    # Aug 31, 2024 is a Saturday -> last trading day rolls back to Fri Aug 30.
    series = ListedSeries(series_id="X", expiry_year=2024, expiry_month=8)
    assert series.last_trading_day == date(2024, 8, 30)
    assert series.due_day == date(2024, 8, 31)
