import polars as pl
import pytest

from mq.io.grid import nearest_cell


def test_nearest_cell_picks_closest_point() -> None:
    df = pl.DataFrame(
        {
            "lat": [10.0, 10.25, 11.0],
            "lon": [80.0, 80.0, 80.0],
            "rain_mm": [1.0, 2.0, 3.0],
        }
    )
    lat, lon = nearest_cell(df, lat=10.1, lon=80.0)
    assert (lat, lon) == (10.0, 80.0)


def test_nearest_cell_works_with_many_duplicate_rows_per_cell() -> None:
    # Simulates the real shape: many (date) rows share the same (lat, lon).
    rows = []
    for d in range(100):
        rows.append({"lat": 10.0, "lon": 80.0, "day": d})
        rows.append({"lat": 20.0, "lon": 90.0, "day": d})
    df = pl.DataFrame(rows)
    lat, lon = nearest_cell(df, lat=19.9, lon=89.9)
    assert (lat, lon) == (20.0, 90.0)


def test_nearest_cell_raises_on_empty_grid() -> None:
    df = pl.DataFrame({"lat": [], "lon": []}, schema={"lat": pl.Float64, "lon": pl.Float64})
    with pytest.raises(ValueError, match="empty"):
        nearest_cell(df, lat=0.0, lon=0.0)
