"""Golden test for `build_live_feature_row` (M7's live-forecast gap).
Reuses the exact fixture from `test_forecasting_features_golden.py`
(same spec, same 2021-2022 LPA base giving per-day LPA [6, 2, 3] for
Sep1/2/3), extended with a THIRD, partial season (2028, Sep1-Sep2
only -- an in-progress season, which `build_training_rows` could never
include) to exercise the live-row path specifically.

2028 avg rainfall [4.5, 1.5] (station a=[4.0,2.0], b=[5.0,1.0]),
deviation from LPA [6,2]: [-1.5, -0.5]
  as_of=2028-09-01: cum_deviation=-1.5, days_remaining=(Sep3-Sep1)=2
  as_of=2028-09-02: cum_deviation=-1.5-0.5=-2.0, days_remaining=1

No 2028 ONI/DMI exists in the fixture -- `build_live_feature_row` must
fall back to the latest *published* value (2027-09-15: oni=-1.1,
dmi=0.3), not fail or guess, per its own real-world-latency fix.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from mq.forecasting.features import build_live_feature_row
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
    for year in (2021, 2022):  # LPA base years, identical both years -> LPA [6, 2, 3]
        rows += [
            {"date": date(year, 9, 1), "lat": 13.0, "lon": 80.0, "rain_mm": 2.0},
            {"date": date(year, 9, 2), "lat": 13.0, "lon": 80.0, "rain_mm": 4.0},
            {"date": date(year, 9, 3), "lat": 13.0, "lon": 80.0, "rain_mm": 6.0},
            {"date": date(year, 9, 1), "lat": 14.0, "lon": 81.0, "rain_mm": 10.0},
            {"date": date(year, 9, 2), "lat": 14.0, "lon": 81.0, "rain_mm": 0.0},
            {"date": date(year, 9, 3), "lat": 14.0, "lon": 81.0, "rain_mm": 0.0},
        ]
    # 2028: partial, in-progress season -- Sep1-Sep2 only, no Sep3.
    rows += [
        {"date": date(2028, 9, 1), "lat": 13.0, "lon": 80.0, "rain_mm": 4.0},
        {"date": date(2028, 9, 2), "lat": 13.0, "lon": 80.0, "rain_mm": 2.0},
        {"date": date(2028, 9, 1), "lat": 14.0, "lon": 81.0, "rain_mm": 5.0},
        {"date": date(2028, 9, 2), "lat": 14.0, "lon": 81.0, "rain_mm": 1.0},
    ]
    return pl.DataFrame(rows)


def _climate_idx() -> pl.DataFrame:
    # Latest published value is 2027-09-15 -- no 2028 entry at all,
    # deliberately, to exercise the "most recently published" fallback.
    rows = [
        {
            "index": "oni",
            "date": date(2026, 9, 15),
            "value": 0.5,
            "release_date": date(2026, 10, 1),
        },
        {
            "index": "dmi",
            "date": date(2026, 9, 15),
            "value": -0.2,
            "release_date": date(2026, 10, 1),
        },
        {
            "index": "oni",
            "date": date(2027, 9, 15),
            "value": -1.1,
            "release_date": date(2027, 10, 1),
        },
        {
            "index": "dmi",
            "date": date(2027, 9, 15),
            "value": 0.3,
            "release_date": date(2027, 10, 1),
        },
    ]
    return pl.DataFrame(rows)


def test_live_row_matches_hand_computed_anomaly_and_days_remaining() -> None:
    row = build_live_feature_row(_spec(), _rain_grid(), _climate_idx(), as_of=date(2028, 9, 2))
    assert row.height == 1
    r = row.row(0, named=True)
    assert r["year"] == 2028
    assert r["observed_to_date_anomaly_mm"] == pytest.approx(-2.0)
    assert r["days_remaining"] == 1


def test_live_row_falls_back_to_latest_published_oni_dmi() -> None:
    row = build_live_feature_row(_spec(), _rain_grid(), _climate_idx(), as_of=date(2028, 9, 2))
    r = row.row(0, named=True)
    assert r["oni"] == pytest.approx(-1.1)
    assert r["dmi"] == pytest.approx(0.3)


def test_live_row_first_day_of_season() -> None:
    row = build_live_feature_row(_spec(), _rain_grid(), _climate_idx(), as_of=date(2028, 9, 1))
    r = row.row(0, named=True)
    assert r["observed_to_date_anomaly_mm"] == pytest.approx(-1.5)
    assert r["days_remaining"] == 2


def test_live_row_raises_outside_open_season_window() -> None:
    with pytest.raises(ValueError, match="outside this contract's open season window"):
        # Sep 3 is this fixture's period_end -- nothing "remaining" to
        # forecast on the season's own last day (same exclusion
        # build_training_rows applies to historical rows).
        build_live_feature_row(_spec(), _rain_grid(), _climate_idx(), as_of=date(2028, 9, 3))


def test_live_row_raises_on_real_data_gap() -> None:
    # A day inside the season window that was simply never ingested --
    # fail loudly, not silently treat a missing day as zero rain.
    gappy_grid = _rain_grid().filter(~(pl.col("date") == date(2028, 9, 2)))
    with pytest.raises(ValueError, match="missing daily rainfall"):
        build_live_feature_row(_spec(), gappy_grid, _climate_idx(), as_of=date(2028, 9, 2))
