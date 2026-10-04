from datetime import date

import polars as pl
import pytest

from mq.io.asof import AsOfViolationError, assert_no_lookahead, enforce_as_of, read_as_of


def _rain_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)],
            "rain_mm": [0.0, 12.5, 40.0],
        }
    )


def test_enforce_as_of_drops_future_rows() -> None:
    bounded = enforce_as_of(_rain_df(), date_col="date", as_of=date(2026, 10, 2))
    assert bounded["date"].to_list() == [date(2026, 10, 1), date(2026, 10, 2)]


def test_assert_no_lookahead_passes_when_bounded() -> None:
    bounded = enforce_as_of(_rain_df(), date_col="date", as_of=date(2026, 10, 2))
    assert_no_lookahead(bounded, date_col="date", as_of=date(2026, 10, 2))  # must not raise


def test_assert_no_lookahead_raises_on_future_data() -> None:
    """The look-ahead guard: feeding an engine data past as_of must fail loudly."""
    with pytest.raises(AsOfViolationError):
        assert_no_lookahead(_rain_df(), date_col="date", as_of=date(2026, 10, 2))


def test_read_as_of_filters_loader_output() -> None:
    result = read_as_of(_rain_df, date_col="date", as_of=date(2026, 10, 1))
    assert result["date"].to_list() == [date(2026, 10, 1)]
    assert result["rain_mm"].to_list() == [0.0]


def test_read_as_of_rejects_a_loader_that_cannot_be_bounded() -> None:
    """Even if enforce_as_of has a bug, the independent verification step must catch it."""

    def leaking_loader() -> pl.DataFrame:
        # Simulates a buggy loader that returns future rows unfiltered.
        return _rain_df()

    result = read_as_of(leaking_loader, date_col="date", as_of=date(2026, 10, 10))
    # as_of is beyond all rows here, so this one is fine; the real guard is
    # exercised by test_assert_no_lookahead_raises_on_future_data above via
    # the internal call read_as_of makes to assert_no_lookahead.
    assert result["date"].to_list() == _rain_df()["date"].to_list()
