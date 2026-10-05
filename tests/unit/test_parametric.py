from __future__ import annotations

import numpy as np
import pytest

from mq.risk.parametric import (
    ParametricCoverParams,
    basis_failure_probability,
    dry_cover_payout,
    optimize_cover,
    payout_for,
    premium,
    wet_cover_payout,
)


def test_wet_cover_payout_hand_computed() -> None:
    index = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    payout = wet_cover_payout(index, trigger=25.0, slope=2.0, limit=20.0)
    # 10,20 -> below trigger -> 0; 30 -> 2*5=10; 40 -> 2*15=30 capped at 20; 50 -> capped at 20
    np.testing.assert_allclose(payout, [0.0, 0.0, 10.0, 20.0, 20.0])


def test_dry_cover_payout_hand_computed() -> None:
    index = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    payout = dry_cover_payout(index, trigger=25.0, slope=2.0, limit=20.0)
    # 10 -> 2*15=30 capped at 20; 20 -> 2*5=10; 30,40,50 -> above trigger -> 0
    np.testing.assert_allclose(payout, [20.0, 10.0, 0.0, 0.0, 0.0])


def test_payout_for_dispatches_on_direction() -> None:
    index = np.array([30.0])
    wet_params = ParametricCoverParams(trigger=25.0, slope=2.0, limit=20.0, direction="wet")
    dry_params = ParametricCoverParams(trigger=25.0, slope=2.0, limit=20.0, direction="dry")
    assert payout_for(index, wet_params)[0] == pytest.approx(10.0)
    assert payout_for(index, dry_params)[0] == pytest.approx(0.0)


def test_parametric_cover_params_rejects_bad_direction() -> None:
    with pytest.raises(ValueError, match="direction"):
        ParametricCoverParams(trigger=1.0, slope=1.0, limit=1.0, direction="sideways")


def test_premium_at_lambda_zero_approaches_physical_mean() -> None:
    rng = np.random.default_rng(0)
    index = rng.normal(900, 300, size=20_000)
    params = ParametricCoverParams(trigger=1000.0, slope=1.0, limit=500.0, direction="wet")
    payout = payout_for(index, params)
    prem = premium(index, params, lam=0.0, loading=0.0)
    assert prem == pytest.approx(float(np.mean(payout)), rel=1e-3)


def test_premium_applies_loading_multiplicatively() -> None:
    rng = np.random.default_rng(1)
    index = rng.normal(900, 300, size=20_000)
    params = ParametricCoverParams(trigger=1000.0, slope=1.0, limit=500.0, direction="wet")
    base = premium(index, params, lam=0.0, loading=0.0)
    loaded = premium(index, params, lam=0.0, loading=0.25)
    assert loaded == pytest.approx(base * 1.25, rel=1e-6)


def test_basis_failure_probability_hand_computed() -> None:
    loss = np.array([500.0, 1000.0, 300.0, 2000.0, 100.0])
    payout = np.array([0.0, 0.0, 10.0, 20.0, 20.0])
    # loss>800: [F,T,F,T,F]; payout==0: [T,T,F,F,F]; AND: [F,T,F,F,F] -> 1/5
    bfp = basis_failure_probability(loss, payout, loss_threshold=800.0)
    assert bfp == pytest.approx(0.2)


def test_basis_failure_probability_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        basis_failure_probability(np.array([1.0, 2.0]), np.array([1.0]), loss_threshold=0.0)


def test_optimize_cover_finds_the_perfectly_triggering_combination() -> None:
    # loss is a deterministic linear function of index -> a wet cover
    # triggered right at the loss-threshold-implied index level should
    # achieve basis_failure_probability == 0 exactly, within budget.
    index = np.linspace(0.0, 100.0, 21)
    loss = index * 10.0
    loss_threshold = 500.0  # loss > 500 <=> index > 50

    result = optimize_cover(
        loss,
        index,
        direction="wet",
        loss_threshold=loss_threshold,
        budget=1000.0,
        lam=0.0,
        loading=0.0,
        trigger_grid=[40.0, 50.0, 60.0],
        slope_grid=[1.0, 5.0, 10.0],
        limit_grid=[50.0, 100.0, 1000.0],
    )

    assert result.basis_failure_probability == pytest.approx(0.0, abs=1e-9)
    assert result.premium <= 1000.0
    assert result.n_grid_evaluated == 27


def test_optimize_cover_raises_when_no_grid_point_respects_budget() -> None:
    index = np.linspace(0.0, 100.0, 21)
    loss = index * 10.0
    with pytest.raises(ValueError, match="budget"):
        optimize_cover(
            loss,
            index,
            direction="wet",
            loss_threshold=500.0,
            budget=0.0001,
            trigger_grid=[50.0],
            slope_grid=[1.0],
            limit_grid=[1000.0],
        )


def test_optimize_cover_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        optimize_cover(
            np.array([1.0, 2.0]),
            np.array([1.0]),
            direction="wet",
            loss_threshold=0.0,
            budget=100.0,
            trigger_grid=[1.0],
            slope_grid=[1.0],
            limit_grid=[1.0],
        )
