from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl
import pytest

from mq.index.lpa import DailyLPA
from mq.pricing.simulator_glm import ChainModel, GLMFit
from mq.risk.greeks import (
    delta,
    full_season_payoff,
    gamma,
    theta_climatological_day,
    theta_no_rain_day,
)


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


def _always_dry_model() -> ChainModel:
    never_wet = GLMFit(kind="logistic", coef=np.array([-50.0]), n_obs=1, converged=True)
    amount = GLMFit(
        kind="gamma_log", coef=np.array([0.0]), n_obs=1, converged=True, extra={"shape": 1.0}
    )
    return ChainModel(
        n_harmonics=0,
        covariate_cols=[],
        occurrence_01=never_wet,
        occurrence_11=never_wet,
        amount=amount,
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


def test_delta_is_exactly_one_for_a_deterministic_model() -> None:
    # always-dry -> terminal_index = obs - const, purely linear in obs,
    # zero variance across paths -> delta must be exactly 1, SE exactly 0.
    model = _always_dry_model()
    lpa = _flat_lpa(2.0)
    result = delta(
        model,
        lpa,
        observed_to_date=500.0,
        start_date=date(2026, 9, 1),
        period_end=date(2026, 9, 10),
        start_state=0,
        covariates=[],
        overdispersion_sd=0.0,
        n_paths=50,
        seed=1,
    )
    assert result.value == pytest.approx(1.0, abs=1e-9)
    assert result.se == pytest.approx(0.0, abs=1e-9)
    assert result.pairing == "exact"


def test_gamma_is_exactly_zero_for_a_deterministic_linear_model() -> None:
    model = _always_dry_model()
    lpa = _flat_lpa(2.0)
    result = gamma(
        model,
        lpa,
        observed_to_date=500.0,
        start_date=date(2026, 9, 1),
        period_end=date(2026, 9, 10),
        start_state=0,
        covariates=[],
        overdispersion_sd=0.0,
        n_paths=50,
        seed=1,
    )
    assert result.value == pytest.approx(0.0, abs=1e-9)


def test_theta_no_rain_day_is_zero_for_an_already_always_dry_model() -> None:
    # Assuming "tomorrow is dry" exactly matches what an always-dry
    # model would simulate anyway -> V(t+1|no-rain) == V(t) exactly.
    model = _always_dry_model()
    lpa = _flat_lpa(2.0)
    result = theta_no_rain_day(
        model,
        lpa,
        observed_to_date=500.0,
        start_date=date(2026, 9, 1),
        period_end=date(2026, 9, 10),
        start_state=0,
        covariates=[],
        overdispersion_sd=0.0,
        n_paths=200,
        seed=1,
    )
    assert result.value == pytest.approx(0.0, abs=1e-6)
    assert result.pairing == "partial"


def test_theta_climatological_day_equals_tomorrows_lpa_for_an_always_dry_model() -> None:
    # Climatological-day theta assumes deviation=0 tomorrow instead of
    # the always-dry model's actual -lpa_mm -> V(t+1) - V(t) = +lpa_mm exactly.
    model = _always_dry_model()
    lpa_mm = 3.5
    lpa = _flat_lpa(lpa_mm)
    result = theta_climatological_day(
        model,
        lpa,
        observed_to_date=500.0,
        start_date=date(2026, 9, 1),
        period_end=date(2026, 9, 10),
        start_state=0,
        covariates=[],
        overdispersion_sd=0.0,
        n_paths=200,
        seed=1,
    )
    assert result.value == pytest.approx(lpa_mm, abs=1e-6)


def test_theta_handles_the_final_day_without_a_further_simulation() -> None:
    # Single-day season (start_date == period_end): V(t) already
    # simulates that one remaining day, and the always-dry model is
    # fully deterministic -- V(t) already equals the "confirmed dry"
    # final value exactly, so there's no new information for a
    # "tomorrow" bump (which is past period_end anyway) to reveal.
    # theta is correctly 0 here, not some nonzero day-of-decay value.
    model = _always_dry_model()
    lpa = _flat_lpa(2.0)
    result = theta_no_rain_day(
        model,
        lpa,
        observed_to_date=500.0,
        start_date=date(2026, 9, 10),
        period_end=date(2026, 9, 10),
        start_state=0,
        covariates=[],
        overdispersion_sd=0.0,
        n_paths=50,
        seed=1,
    )
    assert result.value == pytest.approx(0.0, abs=1e-9)


def test_delta_se_fraction_stays_small_with_common_random_numbers() -> None:
    # Genuinely stochastic model -- SPEC's own acceptance bar (SE < 5%
    # of value) should hold thanks to CRN's exact per-path pairing.
    model = _always_wet_model(mean_log=np.log(10.0), shape=3.0)
    lpa = _flat_lpa(2.0)
    result = delta(
        model,
        lpa,
        observed_to_date=500.0,
        start_date=date(2026, 9, 1),
        period_end=date(2026, 11, 30),
        start_state=1,
        covariates=[],
        overdispersion_sd=0.3,
        n_paths=5000,
        seed=7,
    )
    assert result.value == pytest.approx(1.0, abs=0.05)
    assert result.se_fraction < 0.05


def test_full_season_payoff_raises_when_start_after_period_end() -> None:
    model = _always_dry_model()
    lpa = _flat_lpa(2.0)
    with pytest.raises(ValueError, match="not before"):
        full_season_payoff(
            model,
            lpa,
            observed_to_date=0.0,
            start_date=date(2026, 9, 10),
            period_end=date(2026, 9, 5),
            start_state=0,
            covariates=[],
            overdispersion_sd=0.0,
            n_paths=10,
            seed=1,
        )
