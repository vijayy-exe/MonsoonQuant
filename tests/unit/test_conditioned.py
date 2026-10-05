from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl
import pytest

from mq.index.lpa import DailyLPA
from mq.pricing.conditioned import forecast_conditioned_payoff_distribution, quantile_map
from mq.pricing.simulator_glm import ChainModel, GLMFit
from mq.pricing.simulator_ref import SimRequest
from mq.pricing.simulator_ref import simulate as simulate_numpy


def test_quantile_map_hand_computed() -> None:
    simulated = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    forecast_quantiles = {0.05: 100.0, 0.25: 200.0, 0.5: 300.0, 0.75: 400.0, 0.95: 500.0}

    mapped = quantile_map(simulated, forecast_quantiles)

    # ranks/(n+1) = [1,2,3,4,5]/6; extrapolated grid: lo_ext=75, hi_ext=525
    # (slope 500/0.2 on both ends -- see hand-derivation in commit message)
    expected = [158.333, 233.333, 300.0, 366.667, 441.667]
    np.testing.assert_allclose(mapped, expected, atol=1e-2)


def test_quantile_map_preserves_rank_order() -> None:
    rng = np.random.default_rng(0)
    simulated = rng.normal(900, 300, size=500)
    forecast_quantiles = {0.05: 300.0, 0.25: 600.0, 0.5: 900.0, 0.75: 1200.0, 0.95: 1600.0}
    mapped = quantile_map(simulated, forecast_quantiles)
    # same permutation sorts both arrays -> rank order preserved
    assert np.all(np.argsort(simulated) == np.argsort(mapped))


def _flat_lpa(lpa_mm: float) -> DailyLPA:
    rows = [(m, d, lpa_mm) for m in range(1, 13) for d in range(1, 32)]
    table = pl.DataFrame(rows, schema=["month", "day", "lpa_mm"], orient="row")
    return DailyLPA(
        cell_lat=0.0,
        cell_lon=0.0,
        base_period_start_year=1991,
        base_period_end_year=2020,
        n_years_by_day={},
        table=table,
    )


def _always_wet_model(*, mean_log: float, shape: float) -> ChainModel:
    always_wet = GLMFit(kind="logistic", coef=np.array([50.0]), n_obs=1, converged=True)
    amount = GLMFit(
        kind="gamma_log", coef=np.array([mean_log]), n_obs=1, converged=True, extra={"shape": shape}
    )
    return ChainModel(
        n_harmonics=0,
        covariate_cols=[],
        occurrence_01=always_wet,
        occurrence_11=always_wet,
        amount=amount,
    )


def test_remainder_decomposition_consistent_with_near_term_and_full_runs() -> None:
    """The "no simulator change needed" claim relies on `simulate_numpy`
    (NumPy's Generator is a sequential, stateful stream) producing
    IDENTICAL draws for days 1..h whether the call asks for n_days=h or
    n_days=H>h, as long as both start from the same seed -- a fresh
    `np.random.default_rng(seed)` replays the identical sequence of
    `rng.random(n)`/`rng.gamma(...)` calls through iteration h-1
    regardless of how many further iterations follow. Checked here via
    a large-n_paths law-of-large-numbers comparison against each run's
    closed-form expected deviation (mean_amt - lpa_mm per day, since
    this fixture is always-wet): near_term's mean should track h days'
    worth, full's mean should track total_days' worth, and
    full-minus-near_term (the remainder this module actually computes)
    should track the remaining (total_days - h) days' worth -- an
    internal-consistency check of the subtraction, not of RNG internals
    directly, but it would fail if the two calls silently used
    different per-day distributions for the shared days."""
    mean_amt = 10.0
    lpa_mm = 2.0
    model = _always_wet_model(mean_log=np.log(mean_amt), shape=3.0)
    lpa = _flat_lpa(lpa_mm)
    h = 5
    total_days = 12
    seed = 777
    n_paths = 50_000
    expected_daily_deviation = mean_amt - lpa_mm

    def run(n_days: int) -> np.ndarray:
        return simulate_numpy(
            model,
            lpa,
            SimRequest(
                n_paths=n_paths,
                start_date=date(2026, 9, 1),
                n_days=n_days,
                seed=seed,
                observed_to_date=0.0,
                start_state=1,
                covariates=[],
            ),
        ).terminal_index

    near_term = run(h)
    full = run(total_days)
    remainder = full - near_term

    assert near_term.mean() == pytest.approx(h * expected_daily_deviation, rel=0.02)
    assert full.mean() == pytest.approx(total_days * expected_daily_deviation, rel=0.02)
    assert remainder.mean() == pytest.approx((total_days - h) * expected_daily_deviation, rel=0.02)


def test_forecast_conditioned_payoff_when_horizon_covers_whole_season() -> None:
    model = _always_wet_model(mean_log=np.log(10.0), shape=3.0)
    lpa = _flat_lpa(2.0)
    forecast_quantiles = {0.05: 30.0, 0.25: 40.0, 0.5: 50.0, 0.75: 60.0, 0.95: 70.0}

    result = forecast_conditioned_payoff_distribution(
        model,
        lpa,
        observed_to_date=100.0,
        start_date=date(2026, 9, 1),
        period_end=date(2026, 9, 5),  # 5-day season
        start_state=1,
        covariates=[],
        overdispersion_sd=0.0,
        forecast_quantiles=forecast_quantiles,
        horizon_days=5,  # covers the whole remaining season -> no separate remainder call
        n_paths=200,
        seed=42,
    )

    assert result.horizon_days == 5
    assert result.n_paths == 200
    assert result.payoff.shape == (200,)
    # horizon covers the whole season -> payoff is exactly
    # observed_to_date + quantile-mapped near-term rain - lpa_sum_over_window
    # (lpa_mm=2.0/day * 5 days = 10.0). Median rank maps to the forecast's
    # own q=0.5 value (50.0) -> expected median payoff = 100+50-10 = 140.
    assert np.median(result.payoff) == pytest.approx(140.0, abs=5.0)
    assert result.band_width_90 >= 0.0


def test_forecast_conditioned_payoff_raises_when_start_date_not_before_period_end() -> None:
    model = _always_wet_model(mean_log=np.log(10.0), shape=3.0)
    lpa = _flat_lpa(2.0)
    with pytest.raises(ValueError, match="not before"):
        forecast_conditioned_payoff_distribution(
            model,
            lpa,
            observed_to_date=0.0,
            start_date=date(2026, 9, 10),
            period_end=date(2026, 9, 5),
            start_state=0,
            covariates=[],
            overdispersion_sd=0.0,
            forecast_quantiles={0.5: 10.0, 0.25: 5.0, 0.75: 15.0},
            horizon_days=5,
            n_paths=10,
            seed=1,
        )
