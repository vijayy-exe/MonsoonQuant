from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl
import pytest

from mq.index.lpa import DailyLPA
from mq.pricing.simulator_glm import ChainModel, GLMFit
from mq.pricing.simulator_ref import SimRequest, calibrate_overdispersion_sd, simulate


def _flat_lpa(lpa_mm: float, *, months: range = range(1, 13)) -> DailyLPA:
    rows = [(m, d, lpa_mm) for m in months for d in range(1, 32)]
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
    # intercept-only design (n_harmonics=0 -> 1 column); a very negative
    # intercept makes P(wet) effectively 0 for both p01 and p11.
    never_wet = GLMFit(kind="logistic", coef=np.array([-50.0]), n_obs=1, converged=True)
    flat_amount = GLMFit(
        kind="gamma_log", coef=np.array([0.0]), n_obs=1, converged=True, extra={"shape": 1.0}
    )
    return ChainModel(
        n_harmonics=0,
        covariate_cols=[],
        occurrence_01=never_wet,
        occurrence_11=never_wet,
        amount=flat_amount,
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


def test_always_dry_model_gives_deterministic_terminal_index() -> None:
    model = _always_dry_model()
    lpa = _flat_lpa(2.0)
    req = SimRequest(
        n_paths=50,
        start_date=date(2026, 9, 1),
        n_days=10,
        seed=42,
        observed_to_date=100.0,
        start_state=0,
        covariates=[],
    )

    result = simulate(model, lpa, req)

    # no rain ever falls -> every day's deviation is exactly -lpa_mm
    expected = 100.0 + 10 * (-2.0)
    np.testing.assert_allclose(result.terminal_index, expected)
    np.testing.assert_allclose(result.seasonal_total_mm, 0.0)


def test_same_seed_gives_bit_identical_output() -> None:
    model = _always_wet_model(mean_log=np.log(10.0), shape=2.0)
    lpa = _flat_lpa(5.0)
    req = SimRequest(
        n_paths=200,
        start_date=date(2026, 9, 1),
        n_days=30,
        seed=7,
        observed_to_date=0.0,
        start_state=1,
        covariates=[],
        overdispersion_sd=0.3,
    )

    r1 = simulate(model, lpa, req)
    r2 = simulate(model, lpa, req)

    np.testing.assert_array_equal(r1.terminal_index, r2.terminal_index)
    np.testing.assert_array_equal(r1.seasonal_total_mm, r2.seasonal_total_mm)


def test_always_wet_mean_seasonal_total_converges_to_glm_mean_times_days() -> None:
    mean_per_day = 10.0
    model = _always_wet_model(mean_log=np.log(mean_per_day), shape=4.0)
    lpa = _flat_lpa(0.0)
    req = SimRequest(
        n_paths=20_000,
        start_date=date(2026, 9, 1),
        n_days=20,
        seed=1,
        observed_to_date=0.0,
        start_state=1,
        covariates=[],
    )

    result = simulate(model, lpa, req)

    expected_total = mean_per_day * 20
    assert np.mean(result.seasonal_total_mm) == pytest.approx(expected_total, rel=0.03)


def test_overdispersion_increases_seasonal_total_variance() -> None:
    model = _always_wet_model(mean_log=np.log(10.0), shape=4.0)
    lpa = _flat_lpa(0.0)
    base_req = SimRequest(
        n_paths=20_000,
        start_date=date(2026, 9, 1),
        n_days=30,
        seed=3,
        observed_to_date=0.0,
        start_state=1,
        covariates=[],
    )
    no_fix = simulate(model, lpa, base_req)
    with_fix = simulate(
        model,
        lpa,
        SimRequest(**{**base_req.__dict__, "overdispersion_sd": 0.5}),
    )

    assert np.std(with_fix.seasonal_total_mm) > np.std(no_fix.seasonal_total_mm)


def test_calibrate_overdispersion_sd_matches_target_within_tolerance() -> None:
    model = _always_wet_model(mean_log=np.log(10.0), shape=4.0)
    lpa = _flat_lpa(0.0)
    template = SimRequest(
        n_paths=4000,
        start_date=date(2026, 9, 1),
        n_days=30,
        seed=5,
        observed_to_date=0.0,
        start_state=1,
        covariates=[],
    )
    # No-fix baseline sd, to pick an achievable target comfortably above it.
    baseline_sd = float(np.std(simulate(model, lpa, template).seasonal_total_mm, ddof=1))
    target = baseline_sd * 1.5

    sigma = calibrate_overdispersion_sd(
        model, lpa, template, target_seasonal_total_sd=target, calibration_n_paths=8000
    )

    check_req = SimRequest(**{**template.__dict__, "overdispersion_sd": sigma, "n_paths": 30_000})
    achieved_sd = float(np.std(simulate(model, lpa, check_req).seasonal_total_mm, ddof=1))
    assert achieved_sd == pytest.approx(target, rel=0.1)
