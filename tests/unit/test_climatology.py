from datetime import date

import polars as pl
import pytest

from mq.forecasting.climatology import (
    enso_conditioned_remaining_rain_forecast,
    remaining_rain_climatology,
)


def _rain_grid_two_cells_two_years() -> pl.DataFrame:
    rows = []
    for year in (2021, 2022):
        for month, day, rain in [(10, 1, 5.0), (10, 2, 10.0), (10, 3, 0.0)]:
            rows.append(
                {"date": date(year, month, day), "lat": 13.0, "lon": 80.25, "rain_mm": rain}
            )
            rows.append(
                {"date": date(year, month, day), "lat": 19.0, "lon": 72.75, "rain_mm": 99.0}
            )
    return pl.DataFrame(rows)


def test_picks_nearest_cell_and_sums_remaining_window() -> None:
    df = _rain_grid_two_cells_two_years()
    forecast = remaining_rain_climatology(
        df, lat=13.08, lon=80.27, as_of=date(2026, 10, 1), period_end_month=10, period_end_day=3
    )
    assert forecast.cell_lat == 13.0
    assert forecast.cell_lon == 80.25
    assert forecast.n_years == 2
    # Each year: 5.0 + 10.0 + 0.0 = 15.0 mm, identical both years.
    assert forecast.sample_values == [15.0, 15.0]
    assert forecast.quantiles["0.5"] == 15.0


def test_partial_window_from_mid_period() -> None:
    df = _rain_grid_two_cells_two_years()
    forecast = remaining_rain_climatology(
        df, lat=13.0, lon=80.25, as_of=date(2026, 10, 2), period_end_month=10, period_end_day=3
    )
    # From Oct 2 onward each year: 10.0 + 0.0 = 10.0mm
    assert forecast.sample_values == [10.0, 10.0]


def test_raises_when_no_historical_years_available() -> None:
    df = pl.DataFrame({"date": [], "lat": [], "lon": [], "rain_mm": []}).cast(
        {"date": pl.Date, "lat": pl.Float64, "lon": pl.Float64, "rain_mm": pl.Float64}
    )
    with pytest.raises(ValueError, match="empty"):
        remaining_rain_climatology(
            df, lat=13.0, lon=80.0, as_of=date(2026, 10, 1), period_end_month=12, period_end_day=31
        )


def _training_rows_9_years() -> pl.DataFrame:
    # oni = year_index (1..9), sorted ascending with no ties ->
    # oni_terciles' cutoffs land at values[3]=4 and values[6]=7, giving
    # tercile0={oni<=4} (years 2001-2004), tercile1={5,6} (2005-2006),
    # tercile2={oni>=7} (2007-2009). target_year=2002 (oni=2) is in
    # tercile0; its OTHER tercile0 analogs are 2001(oni1), 2003(oni3),
    # 2004(oni4) -- exactly 3 years.
    years = list(range(2001, 2010))
    onis = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    # distinct, easily-recognizable target values per year so the test
    # can assert exactly which years' samples came back.
    targets = [100.0, 999.0, 101.0, 102.0, 500.0, 600.0, 700.0, 800.0, 900.0]
    return pl.DataFrame(
        {
            "year": years,
            "issue_date": [date(y, 9, 1) for y in years],
            "issue_month": [9] * 9,
            "issue_day": [1] * 9,
            "days_remaining": [30] * 9,
            "observed_to_date_anomaly_mm": [0.0] * 9,
            "oni": onis,
            "dmi": [0.0] * 9,
            "target_remaining_rain_mm": targets,
        }
    )


def test_enso_forecast_uses_matching_tercile_group() -> None:
    rows = _training_rows_9_years()
    forecast = enso_conditioned_remaining_rain_forecast(
        rows, target_year=2002, issue_date=date(2001, 9, 1), min_group_size=3
    )
    assert forecast.target_oni == 2.0
    assert forecast.target_tercile == 0
    assert not forecast.used_fallback
    assert forecast.n_in_group == 3
    assert sorted(forecast.sample_values) == [100.0, 101.0, 102.0]


def test_enso_forecast_falls_back_when_group_too_small() -> None:
    rows = _training_rows_9_years()
    forecast = enso_conditioned_remaining_rain_forecast(
        rows, target_year=2002, issue_date=date(2001, 9, 1), min_group_size=4
    )
    assert forecast.used_fallback
    assert forecast.n_in_group == 8  # all other years
    assert sorted(forecast.sample_values) == sorted(
        [100.0, 101.0, 102.0, 500.0, 600.0, 700.0, 800.0, 900.0]
    )


def test_enso_forecast_raises_when_target_year_missing() -> None:
    rows = _training_rows_9_years()
    with pytest.raises(ValueError, match="no training row"):
        enso_conditioned_remaining_rain_forecast(
            rows, target_year=1999, issue_date=date(2001, 9, 1)
        )
