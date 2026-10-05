from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from mq.forecasting.analog import analog_forecast


def _training_rows() -> pl.DataFrame:
    # oni and dmi held constant across all "other" years AND equal to
    # the target's own oni/dmi -> those two dims contribute exactly 0
    # to every standardized distance (std forced to 1 when the raw std
    # is 0), leaving distance ordering determined entirely by the
    # anomaly feature -- hand-computable without a calculator mistake
    # hiding in a 3-D Euclidean distance.
    #
    # anomaly = [10, 20, 30, 40, 50] for years 2001..2005; target
    # (2010) anomaly = 25. z-scores (mean=30, sd=sqrt(250)=15.8114):
    #   2001: -1.2649   2002: -0.6325   2003: 0.0   2004: 0.6325   2005: 1.2649
    # target z = (25-30)/15.8114 = -0.3162
    # |diff|: 2001=0.9487  2002=0.3162  2003=0.3162  2004=0.9487  2005=1.5811
    # -> nearest two (k=2) are {2002, 2003}.
    years = [2001, 2002, 2003, 2004, 2005, 2010]
    anomalies = [10.0, 20.0, 30.0, 40.0, 50.0, 25.0]
    targets = [100.0, 200.0, 300.0, 400.0, 500.0, -1.0]  # 2010's own target is irrelevant here
    return pl.DataFrame(
        {
            "year": years,
            "issue_date": [date(y, 9, 1) for y in years],
            "issue_month": [9] * 6,
            "issue_day": [1] * 6,
            "days_remaining": [30] * 6,
            "observed_to_date_anomaly_mm": anomalies,
            "oni": [0.0] * 6,
            "dmi": [0.0] * 6,
            "target_remaining_rain_mm": targets,
        }
    )


def test_analog_forecast_picks_the_two_nearest_years() -> None:
    rows = _training_rows()
    forecast = analog_forecast(rows, target_year=2010, issue_date=date(2001, 9, 1), k=2)

    assert set(forecast.analog_years) == {2002, 2003}
    assert sorted(forecast.sample_values) == [200.0, 300.0]
    assert forecast.quantiles["0.5"] == pytest.approx(250.0)


def test_analog_forecast_k_equals_all_other_years() -> None:
    rows = _training_rows()
    forecast = analog_forecast(rows, target_year=2010, issue_date=date(2001, 9, 1), k=5)
    assert set(forecast.analog_years) == {2001, 2002, 2003, 2004, 2005}
    assert sorted(forecast.sample_values) == [100.0, 200.0, 300.0, 400.0, 500.0]


def test_analog_forecast_raises_when_k_exceeds_available_years() -> None:
    rows = _training_rows()
    with pytest.raises(ValueError, match="only 5 analog"):
        analog_forecast(rows, target_year=2010, issue_date=date(2001, 9, 1), k=6)


def test_analog_forecast_raises_when_target_year_missing() -> None:
    rows = _training_rows()
    with pytest.raises(ValueError, match="no training row"):
        analog_forecast(rows, target_year=1999, issue_date=date(2001, 9, 1), k=2)
