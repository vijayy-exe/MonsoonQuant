"""IMD pipeline tests against a synthetic xarray Dataset — no live network
or real imdlib download."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from mq.pipelines.imd import (
    DQGateFailedError,
    fetch_imd_rain_year,
    run_rain_grid_dq,
    write_rain_grid_year,
)


def _fake_imd_object(dates: pd.DatetimeIndex, lats: list[float], lons: list[float]) -> MagicMock:
    rain = np.full((len(dates), len(lats), len(lons)), 12.5)
    rain[0, 0, 0] = np.nan  # ocean/no-data cell — must be dropped
    ds = xr.Dataset(
        {"rain": (("time", "lat", "lon"), rain)},
        coords={"time": dates, "lat": lats, "lon": lons},
    )
    fake = MagicMock()
    fake.get_xarray.return_value = ds
    return fake


def test_fetch_imd_rain_year_drops_nulls_and_renames_columns(tmp_path: Path) -> None:
    dates = pd.date_range("2023-01-01", periods=2, freq="D")
    fake = _fake_imd_object(dates, lats=[10.0, 10.25], lons=[77.0, 77.25])
    with patch("mq.pipelines.imd.imdlib.get_data", return_value=fake):
        df = fetch_imd_rain_year(2023, raw_dir=tmp_path)

    assert set(df.columns) == {"date", "lat", "lon", "rain_mm", "product_version", "raw_sha256"}
    assert df.height == 2 * 2 * 2 - 1  # one NaN cell dropped
    assert df.filter((df["lat"] == 10.0) & (df["lon"] == 77.25))["rain_mm"].to_list()[0] == 12.5


def test_write_rain_grid_year_blocks_publication_on_incomplete_year(tmp_path: Path) -> None:
    # Only 2 days of a 365-day year present -> DQ01 must fail the gate.
    dates = pd.date_range("2023-01-01", periods=2, freq="D")
    fake = _fake_imd_object(dates, lats=[10.0], lons=[77.0])
    raw_dir = tmp_path / "raw"
    parquet_dir = tmp_path / "parquet"
    with (
        patch("mq.pipelines.imd.imdlib.get_data", return_value=fake),
        pytest.raises(DQGateFailedError) as excinfo,
    ):
        write_rain_grid_year(2023, raw_dir=raw_dir, parquet_dir=parquet_dir)

    assert any(f.check_id == "DQ01" for f in excinfo.value.failures)
    assert not (parquet_dir / "source=imd" / "year=2023").exists()


def test_run_rain_grid_dq_passes_on_a_complete_well_formed_year() -> None:
    from datetime import date, timedelta

    import polars as pl

    all_days = [date(2023, 1, 1) + timedelta(days=i) for i in range(365)]
    df = pl.DataFrame(
        {
            "date": all_days,
            "lat": [10.0] * 365,
            "lon": [77.0] * 365,
            "rain_mm": [1.0] * 365,
            "product_version": ["imdlib-0.25deg-v1"] * 365,
            "raw_sha256": ["abc123"] * 365,
        }
    )
    results = run_rain_grid_dq(df, year=2023)
    assert all(r.status == "pass" for r in results)
