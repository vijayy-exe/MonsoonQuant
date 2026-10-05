from __future__ import annotations

import numpy as np
import pytest

from mq.mpr.esscher import (
    LowEffectiveSampleSizeError,
    effective_sample_size,
    esscher_price,
    esscher_weights,
)


def test_esscher_weights_sum_to_one() -> None:
    payoffs = np.random.default_rng(0).normal(900, 300, size=500)
    weights = esscher_weights(payoffs, theta=0.5)
    assert weights.sum() == pytest.approx(1.0)
    assert np.all(weights >= 0)


def test_esscher_theta_zero_gives_uniform_weights_and_sample_mean() -> None:
    rng = np.random.default_rng(1)
    payoffs = rng.normal(900, 300, size=1000)
    weights = esscher_weights(payoffs, theta=0.0)
    np.testing.assert_allclose(weights, np.full(1000, 1.0 / 1000))
    assert esscher_price(payoffs, theta=0.0) == pytest.approx(float(np.mean(payoffs)))


def test_esscher_positive_theta_increases_price_above_mean() -> None:
    rng = np.random.default_rng(2)
    payoffs = rng.normal(900, 300, size=20_000)
    p_mean = float(np.mean(payoffs))
    assert esscher_price(payoffs, theta=0.3) > p_mean
    assert esscher_price(payoffs, theta=0.8) > esscher_price(payoffs, theta=0.3)


def test_esscher_negative_theta_decreases_price_below_mean() -> None:
    rng = np.random.default_rng(3)
    payoffs = rng.normal(900, 300, size=20_000)
    p_mean = float(np.mean(payoffs))
    assert esscher_price(payoffs, theta=-0.3) < p_mean


def test_effective_sample_size_is_n_for_uniform_weights() -> None:
    weights = np.full(100, 1.0 / 100)
    assert effective_sample_size(weights) == pytest.approx(100.0)


def test_effective_sample_size_collapses_for_concentrated_weights() -> None:
    weights = np.zeros(100)
    weights[0] = 1.0
    assert effective_sample_size(weights) == pytest.approx(1.0)


def test_esscher_refuses_when_ess_too_low() -> None:
    # One extreme outlier plus an aggressive theta concentrates nearly
    # all weight on the outlier -> ESS collapses well below 1% of n.
    payoffs = np.concatenate([np.full(999, 900.0), [50_000.0]])
    with pytest.raises(LowEffectiveSampleSizeError):
        esscher_price(payoffs, theta=3.0, min_ess_fraction=0.01)
