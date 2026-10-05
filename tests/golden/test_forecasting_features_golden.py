"""Golden test for the forecasting-ladder training-row builder (SPEC
§7.6, M7). Reuses the exact 2-station, 3-day CDR fixture from
test_burn_golden.py (same LPA base period 2021-2022, per-day LPA
[6, 2, 3], same 2026/2027 seasons) so the hand-computed deviation
values ([-3.5, 8.5, 2.0] for 2026, [0.5, -1.0, -2.5] for 2027) are
already independently verified there; this test only has to hand-check
the NEW pieces: the cumulative-anomaly-via-cumsum, the
total-minus-cumsum target, and the ONI/DMI join.

Season 2026: avg rainfall [2.5, 10.5, 5.0], deviation [-3.5, 8.5, 2.0],
total_rain = 18.0
  issue=Sep1: cum_deviation=-3.5, cum_rain=2.5 -> target=18.0-2.5=15.5, days_remaining=2
  issue=Sep2: cum_deviation=-3.5+8.5=5.0, cum_rain=13.0 -> target=18.0-13.0=5.0, days_remaining=1
  (Sep3 excluded: it's period_end, nothing remains to forecast)

Season 2027: avg rainfall [6.5, 1.0, 0.5], deviation [0.5, -1.0, -2.5],
total_rain = 8.0
  issue=Sep1: cum_deviation=0.5, cum_rain=6.5 -> target=8.0-6.5=1.5, days_remaining=2
  issue=Sep2: cum_deviation=0.5-1.0=-0.5, cum_rain=7.5 -> target=8.0-7.5=0.5, days_remaining=1
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from mq.forecasting.features import build_training_rows
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


def _climate_idx() -> pl.DataFrame:
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


def test_training_rows_match_hand_computed_anomaly_and_target() -> None:
    rows = build_training_rows(_spec(), _rain_grid(), _climate_idx(), years=[2026, 2027])
    rows = rows.sort(["year", "issue_date"])

    expected = {
        (2026, date(2026, 9, 1)): (-3.5, 15.5, 2),
        (2026, date(2026, 9, 2)): (5.0, 5.0, 1),
        (2027, date(2027, 9, 1)): (0.5, 1.5, 2),
        (2027, date(2027, 9, 2)): (-0.5, 0.5, 1),
    }
    assert rows.height == 4
    for row in rows.iter_rows(named=True):
        anomaly, target, days_remaining = expected[(row["year"], row["issue_date"])]
        assert row["observed_to_date_anomaly_mm"] == pytest.approx(anomaly)
        assert row["target_remaining_rain_mm"] == pytest.approx(target)
        assert row["days_remaining"] == days_remaining


def test_training_rows_join_oni_dmi_correctly() -> None:
    rows = build_training_rows(_spec(), _rain_grid(), _climate_idx(), years=[2026, 2027])
    for row in rows.iter_rows(named=True):
        if row["year"] == 2026:
            assert row["oni"] == pytest.approx(0.5)
            assert row["dmi"] == pytest.approx(-0.2)
        else:
            assert row["oni"] == pytest.approx(-1.1)
            assert row["dmi"] == pytest.approx(0.3)


def test_training_rows_skip_year_without_full_season_coverage() -> None:
    # 2029 has no rain_grid rows at all -> must be silently dropped.
    rows = build_training_rows(_spec(), _rain_grid(), _climate_idx(), years=[2026, 2027, 2029])
    assert set(rows["year"].unique().to_list()) == {2026, 2027}


def test_training_rows_skip_rows_without_covariate_coverage() -> None:
    # Climate index has no rows at all -> every row is dropped (not an
    # error -- an honest "nothing to join" outcome), raised as ValueError
    # since the training-row table would otherwise be empty.
    with pytest.raises(ValueError, match="no training rows"):
        build_training_rows(
            _spec(), _rain_grid(), pl.DataFrame(schema=_climate_idx().schema), years=[2026]
        )
