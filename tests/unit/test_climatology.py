from datetime import date

import polars as pl
import pytest

from mq.forecasting.climatology import remaining_rain_climatology


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
