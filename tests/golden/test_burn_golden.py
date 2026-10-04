"""Golden test for historical burn analysis (SPEC §7.3, §11).

Reuses the 2-station, 3-day CDR setup from test_index_engine_golden.py
(same LPA base period 2021-2022, anchor = 11.0, per-day LPA = [6, 2, 3])
across 3 distinct "historical seasons" with hand-computed final spot
values, then hand-verifies the burn statistics independently via Python's
`statistics` module (not polars) as the cross-check.

Season 2026: Station A rain [5,1,8], Station B rain [0,20,2]
  -> avg rainfall [2.5, 10.5, 5.0] -> deviation [-3.5, 8.5, 2.0]
  -> spot: 11-3.5=7.5, 7.5+8.5=16.0, 16.0+2.0=18.0  => final = 18.0

Season 2027: Station A rain [3,2,1], Station B rain [10,0,0]
  -> avg rainfall [6.5, 1.0, 0.5] -> deviation [0.5, -1.0, -2.5]
  -> spot: 11+0.5=11.5, 11.5-1=10.5, 10.5-2.5=8.0  => final = 8.0

Season 2028: Station A rain [0,0,0], Station B rain [0,0,0]
  -> avg rainfall [0,0,0] -> deviation [-6,-2,-3]
  -> spot: 11-6=5, 5-2=3, 3-3=0  => final = 0.0

Burn sample = [18.0, 8.0, 0.0] (n=3)
  mean   = 26/3 = 8.6666...
  median = 8.0
  sd (sample, ddof=1) = 9.0185... (statistics.stdev cross-check below)
  es_lower_5pct (tail_n=1) = min = 0.0
  es_upper_5pct (tail_n=1) = max = 18.0
"""

from __future__ import annotations

import statistics
from datetime import date

import polars as pl
import pytest

from mq.pricing.burn import build_burn_sample, compute_burn_stats
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


def test_burn_sample_matches_hand_computed_final_spot_values() -> None:
    sample = build_burn_sample(_spec(), _rain_grid(), years=[2026, 2027, 2028])
    assert sample.years == [2026, 2027, 2028]
    assert sample.payoffs == pytest.approx([18.0, 8.0, 0.0])


def test_burn_stats_match_independent_statistics_module_cross_check() -> None:
    sample = build_burn_sample(_spec(), _rain_grid(), years=[2026, 2027, 2028])
    stats = compute_burn_stats(sample)

    payoffs = [18.0, 8.0, 0.0]
    assert stats.n == 3
    assert stats.mean == pytest.approx(statistics.mean(payoffs))
    assert stats.median == pytest.approx(statistics.median(payoffs))
    assert stats.sd == pytest.approx(statistics.stdev(payoffs))  # ddof=1, matches polars default
    assert stats.es_lower_5pct == pytest.approx(0.0)  # tail_n=1 -> the single worst outcome
    assert stats.es_upper_5pct == pytest.approx(18.0)  # tail_n=1 -> the single best outcome


def test_build_burn_sample_skips_years_without_full_coverage() -> None:
    # 2029 has no data at all in the fixture -> must be silently dropped,
    # not crash or fabricate a value.
    sample = build_burn_sample(_spec(), _rain_grid(), years=[2026, 2029])
    assert sample.years == [2026]
    assert sample.payoffs == pytest.approx([18.0])


def test_compute_burn_stats_requires_at_least_two_seasons() -> None:
    sample = build_burn_sample(_spec(), _rain_grid(), years=[2026])
    with pytest.raises(ValueError, match="at least 2"):
        compute_burn_stats(sample)
