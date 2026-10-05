from __future__ import annotations

import numpy as np
import pytest

from mq.risk.hedge import (
    LotConstraints,
    PiecewiseLinearExposure,
    construction_downtime_loss,
    crop_yield_loss,
    delivery_rider_income_loss,
    event_cancellation_loss,
    min_variance_hedge,
)


def test_min_variance_hedge_perfect_correlation_gives_full_effectiveness() -> None:
    # exposure = index - 5 (slope 1) -> h* = -Cov/Var = -1.0 exactly;
    # hedged = exposure + (-1)*index = -5 constant -> zero residual
    # variance -> effectiveness = 1.0 exactly.
    exposure = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    index = np.array([15.0, 25.0, 35.0, 45.0, 55.0])

    result = min_variance_hedge(exposure, index, multiplier=1.0)

    assert result.h_star == pytest.approx(-1.0)
    assert result.lots == -1
    assert result.hedge_effectiveness == pytest.approx(1.0)
    assert result.residual_variance == pytest.approx(0.0, abs=1e-9)


def test_min_variance_hedge_sign_is_opposite_of_basis_hedge_ratio() -> None:
    from mq.risk.basis import compute_basis_stats

    exposure = {2020: 10.0, 2021: 20.0, 2022: 30.0, 2023: 40.0, 2024: 50.0}
    index = {2020: 15.0, 2021: 25.0, 2022: 35.0, 2023: 45.0, 2024: 55.0}
    basis_result = compute_basis_stats(exposure, index)

    hedge_result = min_variance_hedge(
        np.array(list(exposure.values())), np.array(list(index.values())), multiplier=1.0
    )
    assert hedge_result.h_star == pytest.approx(-basis_result.hedge_ratio)


def test_min_variance_hedge_effectiveness_in_zero_one_range() -> None:
    rng = np.random.default_rng(3)
    exposure = rng.normal(100, 30, size=500)
    index = 0.6 * exposure + rng.normal(0, 20, size=500)
    result = min_variance_hedge(exposure, index, multiplier=1.0)
    assert 0.0 <= result.hedge_effectiveness <= 1.0


def test_min_variance_hedge_zero_correlation_gives_h_star_near_zero() -> None:
    rng = np.random.default_rng(0)
    exposure = rng.normal(0, 1, size=500)
    index = rng.normal(0, 1, size=500)
    result = min_variance_hedge(exposure, index, multiplier=1.0)
    assert abs(result.h_star) < 0.2


def test_min_variance_hedge_doubling_exposure_doubles_h_star() -> None:
    rng = np.random.default_rng(1)
    index = rng.normal(500, 100, size=200)
    exposure = 0.5 * index + rng.normal(0, 10, size=200)

    base_result = min_variance_hedge(exposure, index, multiplier=1.0)
    doubled_result = min_variance_hedge(exposure * 2, index, multiplier=1.0)

    assert doubled_result.h_star == pytest.approx(2 * base_result.h_star, rel=1e-6)


def test_min_variance_hedge_respects_lot_constraints() -> None:
    exposure = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    index = np.array([15.0, 25.0, 35.0, 45.0, 55.0])  # h* would be -1.0 lot (unconstrained)

    result = min_variance_hedge(
        exposure, index, multiplier=1.0, constraints=LotConstraints(short_allowed=False)
    )
    assert result.lots == 0  # short disallowed -> clamped to 0, not -1


def test_lot_constraints_bounds_from_margin_and_notional() -> None:
    constraints = LotConstraints(margin_budget=1000.0, margin_per_lot=300.0)
    min_lots, max_lots = constraints.lot_bounds()
    assert max_lots == 3  # floor(1000/300)
    assert min_lots == -3


def test_lot_constraints_long_only() -> None:
    constraints = LotConstraints(short_allowed=False, max_order_lots=5)
    min_lots, max_lots = constraints.lot_bounds()
    assert min_lots == 0
    assert max_lots == 5


def test_piecewise_linear_exposure_clamps_outside_breakpoints() -> None:
    exposure = PiecewiseLinearExposure(
        breakpoints_rain_mm=[0.0, 50.0, 200.0], breakpoints_loss=[0.0, 0.0, 1000.0]
    )
    result = exposure(np.array([-10.0, 0.0, 25.0, 50.0, 125.0, 200.0, 500.0]))
    np.testing.assert_allclose(result, [0.0, 0.0, 0.0, 0.0, 500.0, 1000.0, 1000.0])


def test_piecewise_linear_exposure_rejects_unsorted_breakpoints() -> None:
    with pytest.raises(ValueError, match="sorted"):
        PiecewiseLinearExposure(breakpoints_rain_mm=[50.0, 0.0], breakpoints_loss=[0.0, 1.0])


def test_exposure_templates_have_expected_direction() -> None:
    rain = np.array([0.0, 100.0, 300.0])

    wet_exposure = delivery_rider_income_loss()
    assert wet_exposure(rain)[2] > wet_exposure(rain)[0]  # loss increases with rain

    dry_exposure = crop_yield_loss()
    assert dry_exposure(rain)[0] > dry_exposure(rain)[2]  # loss DEcreases with more rain

    event_exposure = event_cancellation_loss(trigger_mm=50.0, loss=1000.0)
    assert event_exposure(np.array([0.0]))[0] == pytest.approx(0.0)
    assert event_exposure(np.array([100.0]))[0] == pytest.approx(1000.0)

    construction_exposure = construction_downtime_loss()
    assert construction_exposure(rain)[2] > construction_exposure(rain)[0]


def test_min_variance_hedge_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        min_variance_hedge(np.array([1.0, 2.0]), np.array([1.0]), multiplier=1.0)
