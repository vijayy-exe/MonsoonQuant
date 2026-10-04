"""Golden test for the CDR index engine (SPEC §7.2, §11) — the expected
values below are hand-computed, not copied from the implementation. Shown
here so the computation can be checked independently:

Setup: 2 stations, LPA base period 2021-2022, 3-day season (Sep 1-3) to
keep the hand arithmetic small (the real contracts use Sep1-Dec31 /
Jun1-Sep30 — this test exercises the same algorithm, just a short window).

Station A LPA (both base years identical): Sep1=2, Sep2=4, Sep3=6
Station B LPA (both base years identical): Sep1=10, Sep2=0, Sep3=0
  -> Daily LPA (avg of 2 stations): Sep1=6, Sep2=2, Sep3=3
  -> Season LPA anchor = 6+2+3 = 11

2026 (the "current" season) actual rainfall:
Station A: Sep1=5,  Sep2=1,  Sep3=8
Station B: Sep1=0,  Sep2=20, Sep3=2
  -> Daily rainfall (avg): Sep1=2.5, Sep2=10.5, Sep3=5.0
  -> Daily deviation = rainfall - LPA: Sep1=-3.5, Sep2=8.5, Sep3=2.0

Spot (CDR index), starting from the anchor:
  spot(Sep1) = 11 + (-3.5) = 7.5
  spot(Sep2) = 7.5 + 8.5   = 16.0
  spot(Sep3) = 16.0 + 2.0  = 18.0

So observed_to_date as of 2026-09-03 must be 18.0.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from mq.index.engine import compute_index
from mq.specs.contract import (
    ContractSpec,
    IndexDef,
    LPARef,
    MonthDay,
    SettlementRule,
    StationRef,
)

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
    # LPA base years — identical both years so the hand-averaged LPA is exact.
    for year in (2021, 2022):
        rows += [
            {"date": date(year, 9, 1), "lat": 13.0, "lon": 80.0, "rain_mm": 2.0},
            {"date": date(year, 9, 2), "lat": 13.0, "lon": 80.0, "rain_mm": 4.0},
            {"date": date(year, 9, 3), "lat": 13.0, "lon": 80.0, "rain_mm": 6.0},
            {"date": date(year, 9, 1), "lat": 14.0, "lon": 81.0, "rain_mm": 10.0},
            {"date": date(year, 9, 2), "lat": 14.0, "lon": 81.0, "rain_mm": 0.0},
            {"date": date(year, 9, 3), "lat": 14.0, "lon": 81.0, "rain_mm": 0.0},
        ]
    # The current (2026) season's actual rainfall.
    rows += [
        {"date": date(2026, 9, 1), "lat": 13.0, "lon": 80.0, "rain_mm": 5.0},
        {"date": date(2026, 9, 2), "lat": 13.0, "lon": 80.0, "rain_mm": 1.0},
        {"date": date(2026, 9, 3), "lat": 13.0, "lon": 80.0, "rain_mm": 8.0},
        {"date": date(2026, 9, 1), "lat": 14.0, "lon": 81.0, "rain_mm": 0.0},
        {"date": date(2026, 9, 2), "lat": 14.0, "lon": 81.0, "rain_mm": 20.0},
        {"date": date(2026, 9, 3), "lat": 14.0, "lon": 81.0, "rain_mm": 2.0},
    ]
    return pl.DataFrame(rows)


def test_compute_index_matches_hand_calculation_full_season() -> None:
    path = compute_index(_spec(), _rain_grid(), as_of=date(2026, 9, 3))

    assert path.season_lpa_anchor == pytest.approx(11.0)
    assert path.daily_lpa_mm == pytest.approx([6.0, 2.0, 3.0])
    assert path.daily_rainfall_mm == pytest.approx([2.5, 10.5, 5.0])
    assert path.daily_deviation_mm == pytest.approx([-3.5, 8.5, 2.0])
    assert path.spot == pytest.approx([7.5, 16.0, 18.0])
    assert path.observed_to_date == pytest.approx(18.0)


def test_compute_index_mid_season_stops_at_as_of() -> None:
    path = compute_index(_spec(), _rain_grid(), as_of=date(2026, 9, 2))
    assert path.dates == [date(2026, 9, 1), date(2026, 9, 2)]
    assert path.spot == pytest.approx([7.5, 16.0])
    assert path.observed_to_date == pytest.approx(16.0)


def test_compute_index_before_season_start_returns_empty_path() -> None:
    path = compute_index(_spec(), _rain_grid(), as_of=date(2026, 8, 15))
    assert path.dates == []
    assert path.observed_to_date == pytest.approx(path.season_lpa_anchor)


def test_compute_index_raises_on_missing_station_data() -> None:
    df = _rain_grid().filter(~((pl.col("date") == date(2026, 9, 2)) & (pl.col("lat") == 13.0)))
    with pytest.raises(ValueError, match="missing rainfall data"):
        compute_index(_spec(), df, as_of=date(2026, 9, 3))
