from __future__ import annotations

import numpy as np
import pytest

from mq.risk.cvar import empirical_cvar, minimize_cvar_hedge
from mq.risk.hedge import LotConstraints


def test_empirical_cvar_hand_computed() -> None:
    # alpha=0.8, n=5 -> n_tail = round(0.2*5) = 1 -> worst 1 value's mean = max
    losses = np.array([10.0, 20.0, 30.0, 40.0, 100.0])
    assert empirical_cvar(losses, alpha=0.8) == pytest.approx(100.0)

    # alpha=0.6, n=5 -> n_tail = round(0.4*5) = 2 -> mean of worst 2 = (40+100)/2 = 70
    assert empirical_cvar(losses, alpha=0.6) == pytest.approx(70.0)


def test_minimize_cvar_hedge_perfect_correlation_nearly_eliminates_tail_risk() -> None:
    # exposure = index - 5 exactly, with index spanning BOTH signs (like
    # a real CDR deviation can) -- hedged_loss = index*(1+h) - 5, so
    # h=-1 is the unique point making every scenario's hedged loss
    # exactly -5 (constant), regardless of index's sign distribution.
    # An all-positive index (tried first) makes this degenerate: shorting
    # ever more aggressively keeps "improving" CVaR without bound, since
    # there's no scenario whose sign would eventually make that worse --
    # a real two-sided index is what gives CVaR a genuine interior
    # optimum here, matching variance's.
    index = np.array([-40.0, -30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0, 40.0, 50.0])
    exposure = index - 5.0

    result = minimize_cvar_hedge(exposure, index, multiplier=1.0)

    assert result.h_star == pytest.approx(-1.0, abs=1e-4)
    assert result.lots == -1
    assert result.cvar_95 == pytest.approx(-5.0, abs=1e-6)
    assert result.cvar_95 < result.do_nothing_cvar_95


def test_minimize_cvar_hedge_reduces_cvar_relative_to_do_nothing() -> None:
    rng = np.random.default_rng(4)
    index = rng.normal(500, 100, size=200)
    exposure = 0.7 * index + rng.normal(0, 30, size=200)

    result = minimize_cvar_hedge(exposure, index, multiplier=1.0)

    assert result.cvar_95 <= result.do_nothing_cvar_95


def test_minimize_cvar_hedge_respects_lot_constraints() -> None:
    exposure = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0])
    index = exposure + 5.0  # unconstrained optimum is h=-1 lot

    result = minimize_cvar_hedge(
        exposure, index, multiplier=1.0, constraints=LotConstraints(short_allowed=False)
    )
    assert result.lots >= 0


def test_minimize_cvar_hedge_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        minimize_cvar_hedge(np.array([1.0, 2.0]), np.array([1.0]), multiplier=1.0)
