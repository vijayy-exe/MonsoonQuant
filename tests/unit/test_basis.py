from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl
import pytest

from mq.risk.basis import compute_basis_stats, local_index_series, to_geojson
from mq.specs.contract import ContractSpec, IndexDef, LPARef, MonthDay, SettlementRule, StationRef

STATION_A = StationRef(station_id="a", name="Station A", lat=13.0, lon=80.0)
STATION_B = StationRef(station_id="b", name="Station B", lat=14.0, lon=81.0)


def _spec() -> ContractSpec:
    return ContractSpec(
        contract_code="TESTCDR",
        spec_version=date(2026, 1, 1),
        stations=[STATION_A, STATION_B],
        index=IndexDef(
            kind="cumulative_deviation_mm",
            aggregation="mean",
            lpa=LPARef(source_id="test", base_period_start_year=2021, base_period_end_year=2022),
            period_start=MonthDay(month=9, day=1),
            period_end=MonthDay(month=9, day=3),
            missing_data_rule="fail loudly on any gap",
        ),
        multiplier_inr_per_point=50,
        tick_size=1,
        lot_size=1,
        settlement=SettlementRule(method="cash", timing="T+2"),
        source_ids=[],
    )


def _rain_grid() -> pl.DataFrame:
    rows = []
    for year in (2021, 2022):  # LPA base years, identical both years
        rows += [
            {"date": date(year, 9, 1), "lat": 13.0, "lon": 80.0, "rain_mm": 2.0},
            {"date": date(year, 9, 2), "lat": 13.0, "lon": 80.0, "rain_mm": 4.0},
            {"date": date(year, 9, 3), "lat": 13.0, "lon": 80.0, "rain_mm": 6.0},
            {"date": date(year, 9, 1), "lat": 14.0, "lon": 81.0, "rain_mm": 10.0},
            {"date": date(year, 9, 2), "lat": 14.0, "lon": 81.0, "rain_mm": 0.0},
            {"date": date(year, 9, 3), "lat": 14.0, "lon": 81.0, "rain_mm": 0.0},
        ]
    seasons = {
        2026: {"a": [5.0, 1.0, 8.0], "b": [0.0, 20.0, 2.0]},
        2027: {"a": [3.0, 2.0, 1.0], "b": [10.0, 0.0, 0.0]},
        2028: {"a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 0.0]},
    }
    for year, vals in seasons.items():
        for i, day in enumerate((1, 2, 3)):
            rows.append(
                {"date": date(year, 9, day), "lat": 13.0, "lon": 80.0, "rain_mm": vals["a"][i]}
            )
            rows.append(
                {"date": date(year, 9, day), "lat": 14.0, "lon": 81.0, "rain_mm": vals["b"][i]}
            )
    return pl.DataFrame(rows)


def test_local_index_series_matches_hand_computed_single_station_reconstruction() -> None:
    # Station A alone, LPA=[2,4,6] (same base-period data as the burn
    # golden test), reconstructed independently of the 2-station index:
    # 2026: rain=[5,1,8] -> deviation=[3,-3,2] -> spot 12+3=15,15-3=12,12+2=14 -> 14.0
    # 2027: rain=[3,2,1] -> deviation=[1,-2,-5] -> spot 12+1=13,13-2=11,11-5=6 -> 6.0
    # 2028: rain=[0,0,0] -> deviation=[-2,-4,-6] -> spot 12-2=10,10-4=6,6-6=0 -> 0.0
    series = local_index_series(_spec(), _rain_grid(), years=[2026, 2027, 2028], lat=13.0, lon=80.0)
    assert series == pytest.approx({2026: 14.0, 2027: 6.0, 2028: 0.0})


def test_compute_basis_stats_perfect_correlation() -> None:
    local = {2020: 10.0, 2021: 20.0, 2022: 30.0, 2023: 40.0, 2024: 50.0}
    index = {2020: 15.0, 2021: 25.0, 2022: 35.0, 2023: 45.0, 2024: 55.0}  # local + 5, slope 1

    result = compute_basis_stats(local, index)

    assert result.correlation == pytest.approx(1.0)
    assert result.rmse == pytest.approx(5.0)
    assert result.kendall_tau == pytest.approx(1.0)
    assert result.hedge_ratio == pytest.approx(1.0)
    assert result.hedge_effectiveness == pytest.approx(1.0)
    assert result.tail_dependence_upper == pytest.approx(1.0)
    assert result.tail_dependence_lower == pytest.approx(1.0)


def test_compute_basis_stats_hedge_effectiveness_near_zero_for_uncorrelated_exposure() -> None:
    rng = np.random.default_rng(0)
    years = list(range(2000, 2000 + 200))
    local = {y: float(v) for y, v in zip(years, rng.normal(0, 1, size=200), strict=True)}
    index = {y: float(v) for y, v in zip(years, rng.normal(0, 1, size=200), strict=True)}

    result = compute_basis_stats(local, index)

    assert abs(result.hedge_ratio) < 0.2
    assert abs(result.correlation) < 0.2


def test_compute_basis_stats_doubling_exposure_doubles_hedge_ratio() -> None:
    rng = np.random.default_rng(1)
    years = list(range(2000, 2000 + 50))
    index_vals = rng.normal(500, 100, size=50)
    local_vals = 0.5 * index_vals + rng.normal(0, 10, size=50)
    local = {y: float(v) for y, v in zip(years, local_vals, strict=True)}
    doubled_local = {y: float(v) * 2 for y, v in local.items()}
    index = {y: float(v) for y, v in zip(years, index_vals, strict=True)}

    base_result = compute_basis_stats(local, index)
    doubled_result = compute_basis_stats(doubled_local, index)

    assert doubled_result.hedge_ratio == pytest.approx(2 * base_result.hedge_ratio, rel=1e-6)


def test_compute_basis_stats_raises_with_too_few_common_years() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        compute_basis_stats({2020: 1.0, 2021: 2.0}, {2020: 1.0, 2021: 2.0})


def test_compute_basis_stats_only_uses_overlapping_years() -> None:
    local = {2020: 10.0, 2021: 20.0, 2022: 30.0, 2099: 999.0}  # 2099 has no index match
    index = {2020: 10.0, 2021: 20.0, 2022: 30.0}
    result = compute_basis_stats(local, index)
    assert result.n_years == 3
    assert result.correlation == pytest.approx(1.0)


def test_to_geojson_shape() -> None:
    from mq.risk.basis import BasisStats

    cells = [
        BasisStats(
            cell_lat=13.0,
            cell_lon=80.0,
            n_years=3,
            correlation=0.9,
            rmse=5.0,
            kendall_tau=0.8,
            tail_dependence_upper=0.7,
            tail_dependence_lower=0.6,
            seasonal_mismatch=0.1,
            hedge_effectiveness=0.8,
            hedge_ratio=0.95,
        )
    ]
    geojson = to_geojson(cells)
    assert geojson["type"] == "FeatureCollection"
    features = geojson["features"]
    assert isinstance(features, list)
    assert features[0]["geometry"]["coordinates"] == [80.0, 13.0]
    assert features[0]["properties"]["correlation"] == 0.9
