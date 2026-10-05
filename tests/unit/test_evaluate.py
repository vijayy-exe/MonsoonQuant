from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl
import pytest

from mq.forecasting.evaluate import (
    climatology_baseline_forecast,
    crps,
    crpss,
    interval_coverage_hit,
    pinball_loss,
    pit_value,
    reliability_curve,
    walk_forward_backtest,
)

SAMPLES = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
ACTUAL = 30.0


def test_pinball_loss_hand_computed() -> None:
    # quantile(0.5) of SAMPLES == 30.0 exactly -> zero loss at the median.
    assert pinball_loss(SAMPLES, ACTUAL, 0.5) == pytest.approx(0.0)
    # quantile(0.05) == 12.0 (linear interpolation: 10 + 0.2*(20-10));
    # diff = 30-12 = 18 -> pinball = max(0.05*18, -0.95*18) = 0.9
    assert pinball_loss(SAMPLES, ACTUAL, 0.05) == pytest.approx(0.9)


def test_interval_coverage_hit_hand_computed() -> None:
    # level=0.9 -> [quantile(0.05), quantile(0.95)] = [12.0, 48.0]; 30 is inside.
    assert interval_coverage_hit(SAMPLES, ACTUAL, 0.9)
    assert not interval_coverage_hit(SAMPLES, 100.0, 0.9)


def test_pit_value_hand_computed() -> None:
    # 3 of 5 samples (10,20,30) are <= 30.
    assert pit_value(SAMPLES, ACTUAL) == pytest.approx(0.6)


def test_crps_zero_for_a_perfect_deterministic_forecast() -> None:
    assert crps(np.full(50, 42.0), 42.0) == pytest.approx(0.0, abs=1e-9)


def test_crpss_positive_when_model_beats_reference() -> None:
    assert crpss(model_mean_crps=5.0, reference_mean_crps=10.0) == pytest.approx(0.5)
    assert crpss(model_mean_crps=10.0, reference_mean_crps=10.0) == pytest.approx(0.0)
    assert crpss(model_mean_crps=15.0, reference_mean_crps=10.0) < 0


def test_reliability_curve_recovers_known_fractions() -> None:
    # Two pairs, same samples, actuals chosen so q=0.5 is "below" in
    # exactly one of the two cases.
    pairs = [(SAMPLES, 20.0), (SAMPLES, 40.0)]  # quantile(0.5)=30
    curve = reliability_curve(pairs, levels=[0.5])
    # 20 <= 30 -> True; 40 <= 30 -> False -> fraction = 0.5
    assert curve[0.5] == pytest.approx(0.5)


def _climatology_training_rows() -> pl.DataFrame:
    years = list(range(1991, 2001))  # 10 years
    rng = np.random.default_rng(0)
    targets = rng.normal(500, 50, size=len(years))
    return pl.DataFrame(
        {
            "year": years,
            "issue_date": [date(y, 9, 1) for y in years],
            "issue_month": [9] * len(years),
            "issue_day": [1] * len(years),
            "days_remaining": [30] * len(years),
            "observed_to_date_anomaly_mm": [0.0] * len(years),
            "oni": [0.0] * len(years),
            "dmi": [0.0] * len(years),
            "target_remaining_rain_mm": targets,
        }
    )


def test_walk_forward_backtest_produces_sane_result() -> None:
    rows = _climatology_training_rows()
    result = walk_forward_backtest(
        rows, climatology_baseline_forecast, model_id="clim_test", min_train_years=5
    )
    # 10 years, min_train_years=5 -> test years are the last 5 (indices 5..9),
    # one row each (single issue-day fixture) -> 5 predictions.
    assert result.n_predictions == 5
    assert result.mean_crps >= 0
    assert len(result.pit_values) == 5
    assert all(0.0 <= v <= 1.0 for v in result.pit_values)
    assert set(result.coverage_by_level) == {0.5, 0.9}
    assert all(0.0 <= v <= 1.0 for v in result.coverage_by_level.values())


def test_walk_forward_backtest_raises_when_no_predictions_possible() -> None:
    rows = _climatology_training_rows()
    with pytest.raises(ValueError, match="no predictions"):
        walk_forward_backtest(
            rows, climatology_baseline_forecast, model_id="clim_test", min_train_years=20
        )
