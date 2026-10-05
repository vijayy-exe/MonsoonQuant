from __future__ import annotations

import numpy as np
import pytest

from mq.mpr.calibrate import calibrate_wang
from mq.mpr.uncertainty import bayesian_pool, bootstrap_parameter_ci, mc_standard_error
from mq.mpr.wang import wang_price, wang_weights


def test_bootstrap_parameter_ci_covers_true_lambda_with_identity_payoff_fn() -> None:
    rng = np.random.default_rng(0)
    years = list(range(1991, 2021))  # 30 "years"
    true_lambda = 0.5
    # one fixed payoff per year, drawn once -- resampling years with
    # replacement resamples these payoffs with replacement too.
    year_payoff = {
        y: float(v) for y, v in zip(years, rng.normal(900, 300, size=len(years)), strict=True)
    }
    settle = wang_price(np.array(list(year_payoff.values())), true_lambda)

    def payoffs_from_years(resampled_years: list[int]) -> np.ndarray:
        return np.array([year_payoff[y] for y in resampled_years])

    def calibrate_fn(payoffs: np.ndarray) -> float:
        return calibrate_wang(payoffs, settle).param

    result = bootstrap_parameter_ci(
        years, payoffs_from_years, calibrate_fn, n_bootstrap=300, seed=1
    )

    assert result.n_bootstrap == 300
    assert result.lo90 <= result.median <= result.hi90
    # the bootstrap resamples the SAME fixed year->payoff map the
    # settle was computed from, so the median should land close to the
    # true lambda, with a non-degenerate band around it.
    assert result.median == pytest.approx(true_lambda, abs=0.3)
    assert result.hi90 > result.lo90


def test_mc_standard_error_decreases_with_larger_sample() -> None:
    rng = np.random.default_rng(2)
    lam = 0.4

    def se_at_n(n: int) -> float:
        payoffs = rng.normal(900, 300, size=n)
        weights = wang_weights(np.sort(payoffs), lam)
        sorted_payoffs = np.sort(payoffs)

        def price_fn(lam_: float) -> float:
            return wang_price(sorted_payoffs, lam_)

        return mc_standard_error(sorted_payoffs, weights, price_fn, lam)

    se_small = se_at_n(200)
    se_large = se_at_n(20_000)
    assert se_large < se_small


def test_bayesian_pool_single_observation_is_near_the_observation_not_the_prior() -> None:
    result = bayesian_pool(param_estimates=[0.9], standard_errors=[0.05], volumes=[1000.0])
    assert result.posterior_mean == pytest.approx(0.9, abs=0.05)
    assert result.n_obs == 1
    assert result.total_volume == 1000.0


def test_bayesian_pool_with_no_data_reduces_to_prior() -> None:
    # Effectively-uninformative observation (huge standard error) with
    # tiny volume should leave the posterior close to the N(0,1) prior.
    result = bayesian_pool(param_estimates=[5.0], standard_errors=[1000.0], volumes=[1.0])
    assert result.posterior_mean == pytest.approx(0.0, abs=0.05)


def test_bayesian_pool_more_consistent_observations_shrinks_the_band() -> None:
    few = bayesian_pool(param_estimates=[0.5], standard_errors=[0.1], volumes=[100.0])
    many = bayesian_pool(
        param_estimates=[0.5] * 20,
        standard_errors=[0.1] * 20,
        volumes=[100.0] * 20,
    )
    assert many.posterior_sd < few.posterior_sd
    assert (many.hi90 - many.lo90) < (few.hi90 - few.lo90)


def test_bayesian_pool_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        bayesian_pool(param_estimates=[0.1, 0.2], standard_errors=[0.1], volumes=[1.0, 1.0])


def test_bayesian_pool_rejects_zero_total_volume() -> None:
    with pytest.raises(ValueError):
        bayesian_pool(param_estimates=[0.1], standard_errors=[0.1], volumes=[0.0])
