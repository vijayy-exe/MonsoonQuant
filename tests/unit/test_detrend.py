"""Unit tests for SPEC §7.3's detrending options
(`mq.pricing.burn.detrend_sample`) and the out-of-sample selection
between them (`mq.pricing.selection.select_best_detrend*`)."""

from __future__ import annotations

import numpy as np
import pytest

from mq.pricing.burn import BurnSample, detrend_sample
from mq.pricing.selection import CVResult, select_best_detrend_and_distribution


def _sample(payoffs: list[float]) -> BurnSample:
    years = list(range(2000, 2000 + len(payoffs)))
    return BurnSample(contract_code="TESTCDR", years=years, payoffs=payoffs)


def test_detrend_none_is_the_identity_transform() -> None:
    sample = _sample([100.0, 250.0, 80.0, 310.0, 150.0])
    result = detrend_sample(sample, "none")
    assert result.years == sample.years
    assert result.payoffs == pytest.approx(sample.payoffs)


def test_detrend_linear_removes_a_perfect_linear_trend() -> None:
    # payoff = 100 + 10*(year - 2000) exactly -- a pure linear trend, no
    # noise. Residuals are all exactly 0, so every recentered value
    # equals the trend's own value at the final (most recent) year.
    years = list(range(2000, 2010))
    payoffs = [100.0 + 10.0 * (y - 2000) for y in years]
    sample = BurnSample(contract_code="TESTCDR", years=years, payoffs=payoffs)

    result = detrend_sample(sample, "linear")

    final_year_value = payoffs[-1]
    assert result.payoffs == pytest.approx([final_year_value] * len(payoffs), abs=1e-6)


def test_detrend_linear_recenters_a_noisy_trend_to_the_latest_level() -> None:
    rng = np.random.default_rng(0)
    years = list(range(1991, 2021))
    trend = [500.0 + 5.0 * (y - 1991) for y in years]
    noise = rng.normal(0, 20, size=len(years))
    payoffs = [t + float(n) for t, n in zip(trend, noise, strict=True)]
    sample = BurnSample(contract_code="TESTCDR", years=years, payoffs=payoffs)

    result = detrend_sample(sample, "linear")

    # The detrended sample's own mean should sit close to the trend's
    # value at the final year (not the raw sample's historical mean,
    # which is far lower given a strong positive trend).
    assert np.mean(result.payoffs) == pytest.approx(trend[-1], abs=15.0)
    assert np.mean(result.payoffs) > np.mean(payoffs)


def test_detrend_loess_pulls_a_single_point_anomaly_toward_its_flat_neighbors() -> None:
    years = list(range(1991, 2021))
    payoffs = [800.0] * len(years)
    payoffs[15] = 5000.0  # one wild outlier year
    sample = BurnSample("TESTCDR", years, payoffs)

    result = detrend_sample(sample, "loess")

    # The local weighted fit evaluated at the outlier's own position is
    # dominated by its own (maximal, distance-0) weight, so it doesn't
    # collapse to the flat 800 baseline -- but it must move meaningfully
    # off the raw 5000, which a trend-following (not identity) transform
    # must do. Every *other* point, far enough from the anomaly that its
    # own local window excludes it, is untouched (flat 800 stays flat).
    outlier_idx = years.index(1991 + 15)
    assert result.payoffs[outlier_idx] < payoffs[outlier_idx]
    assert result.payoffs[outlier_idx] > 800.0
    for i, year in enumerate(years):
        if abs(year - 2006) > 10:  # outside loess_frac=0.5's ~15-year window
            assert result.payoffs[i] == pytest.approx(800.0, abs=1.0)


def test_detrend_raises_on_a_single_year_sample() -> None:
    # A 1-year sample can't fit any trend -- raise loudly (matching
    # compute_burn_stats's own "need at least 2" guard) rather than let
    # scipy silently return NaN with just a warning.
    sample = _sample([100.0])
    with pytest.raises(ValueError, match="at least 2"):
        detrend_sample(sample, "linear")
    with pytest.raises(ValueError, match="at least 2"):
        detrend_sample(sample, "loess")


def test_select_best_detrend_and_distribution_picks_the_lowest_crps_pair() -> None:
    results = {
        "none": {
            "gamma": CVResult(kind="gamma", n_folds=10, mean_crps=5.0, mean_log_likelihood=-2.0),
            "kde_cv": CVResult(kind="kde_cv", n_folds=10, mean_crps=4.0, mean_log_likelihood=None),
        },
        "linear": {
            "gamma": CVResult(kind="gamma", n_folds=10, mean_crps=3.0, mean_log_likelihood=-1.0),
            "kde_cv": CVResult(kind="kde_cv", n_folds=10, mean_crps=6.0, mean_log_likelihood=None),
        },
        "loess": {
            "gamma": CVResult(kind="gamma", n_folds=10, mean_crps=8.0, mean_log_likelihood=-3.0),
        },
    }
    method, distribution = select_best_detrend_and_distribution(results)
    assert method == "linear"
    assert distribution == "gamma"
