from __future__ import annotations

import numpy as np
import pytest

from mq.mpr.calibrate import calibrate_esscher, calibrate_wang
from mq.mpr.esscher import esscher_price
from mq.mpr.wang import wang_price


def test_calibrate_wang_recovers_known_lambda() -> None:
    rng = np.random.default_rng(0)
    payoffs = rng.normal(900, 300, size=5000)
    true_lambda = 0.8
    settle = wang_price(payoffs, true_lambda)

    result = calibrate_wang(payoffs, settle)

    assert result.converged
    assert result.param == pytest.approx(true_lambda, abs=1e-3)
    assert result.price_at_param == pytest.approx(settle, abs=1e-2)


def test_calibrate_wang_negative_lambda_round_trip() -> None:
    rng = np.random.default_rng(1)
    payoffs = rng.normal(900, 300, size=5000)
    true_lambda = -1.2
    settle = wang_price(payoffs, true_lambda)

    result = calibrate_wang(payoffs, settle)

    assert result.converged
    assert result.param == pytest.approx(true_lambda, abs=1e-3)


def test_calibrate_wang_unreachable_settle_reports_corner_not_converged() -> None:
    rng = np.random.default_rng(2)
    payoffs = rng.normal(900, 300, size=5000)
    absurd_settle = 1e9

    result = calibrate_wang(payoffs, absurd_settle)

    assert not result.converged
    assert result.param in (-3.0, 3.0)


def test_calibrate_esscher_recovers_known_theta() -> None:
    rng = np.random.default_rng(3)
    payoffs = rng.normal(900, 300, size=5000)
    true_theta = 0.6
    settle = esscher_price(payoffs, true_theta)

    result = calibrate_esscher(payoffs, settle)

    assert result.converged
    assert result.param == pytest.approx(true_theta, abs=1e-3)
    assert result.price_at_param == pytest.approx(settle, abs=1e-2)
