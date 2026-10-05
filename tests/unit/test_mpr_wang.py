from __future__ import annotations

import numpy as np
import pytest

from mq.mpr.wang import wang_price, wang_weights


def test_wang_weights_sum_to_one() -> None:
    payoffs = np.sort(np.random.default_rng(0).normal(900, 300, size=500))
    weights = wang_weights(payoffs, lam=0.5)
    assert weights.sum() == pytest.approx(1.0)
    assert np.all(weights > 0)


def test_wang_lambda_zero_is_close_to_identity() -> None:
    rng = np.random.default_rng(1)
    payoffs = rng.normal(900, 300, size=20_000)
    p_mean = float(np.mean(payoffs))
    q_price = wang_price(payoffs, lam=0.0)
    # lambda=0 doesn't make the plotting-position empirical CDF exactly
    # the identity transform, but it should land very close to the
    # plain sample mean at this sample size.
    assert q_price == pytest.approx(p_mean, rel=1e-3)


def test_wang_positive_lambda_increases_price_above_p_mean() -> None:
    # Verified direction (not assumed from a textbook convention — see
    # wang.py's docstring): SPEC's formula F*(x) = Phi(Phi^-1(F(x)) -
    # lambda) makes Q stochastically larger than P for lambda > 0.
    rng = np.random.default_rng(2)
    payoffs = rng.normal(900, 300, size=20_000)
    p_mean = float(np.mean(payoffs))
    assert wang_price(payoffs, lam=0.5) > p_mean
    assert wang_price(payoffs, lam=1.5) > wang_price(payoffs, lam=0.5)


def test_wang_negative_lambda_decreases_price_below_p_mean() -> None:
    rng = np.random.default_rng(3)
    payoffs = rng.normal(900, 300, size=20_000)
    p_mean = float(np.mean(payoffs))
    assert wang_price(payoffs, lam=-0.5) < p_mean


def test_wang_weights_unaffected_by_input_order() -> None:
    rng = np.random.default_rng(4)
    payoffs = rng.normal(900, 300, size=100)
    shuffled = rng.permutation(payoffs)
    assert wang_price(payoffs, lam=0.7) == pytest.approx(wang_price(shuffled, lam=0.7))
