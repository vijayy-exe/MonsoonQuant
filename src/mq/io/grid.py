"""Shared helper for picking the nearest IMD grid cell to a station's
(lat, lon) — used by every engine that reads `rain_grid`-shaped data."""

from __future__ import annotations

import polars as pl


def nearest_cell(rain_grid: pl.DataFrame, *, lat: float, lon: float) -> tuple[float, float]:
    """The (lat, lon) of the grid cell closest to the target point.

    Dedupes to distinct cells *before* computing distance — `rain_grid` is
    one row per (date, cell), so there are far more rows than cells
    (decades of daily data over ~17k land cells). Sorting the full
    dataframe by distance to find a single minimum is a multi-minute,
    multi-GB operation at that scale; sorting ~17k distinct cells is
    instant.
    """
    cells = rain_grid.select("lat", "lon").unique()
    if cells.height == 0:
        raise ValueError("rain_grid is empty — no cell to select")
    nearest = (
        cells.with_columns(
            ((pl.col("lat") - lat) ** 2 + (pl.col("lon") - lon) ** 2).alias("_dist2")
        )
        .sort("_dist2")
        .head(1)
    )
    row = nearest.row(0)
    return float(row[0]), float(row[1])
