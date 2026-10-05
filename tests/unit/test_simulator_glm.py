from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from mq.pricing.simulator_glm import (
    FOURIER_PERIOD_DAYS,
    attach_monthly_covariate,
    build_amount_dataset,
    build_occurrence_dataset,
    fit_gamma_log_link,
    fit_logistic,
    fourier_design,
    predict_gamma_mean,
    predict_logistic,
)


def test_fourier_design_matches_hand_computed_sin_cos() -> None:
    doy = np.array([0.0, FOURIER_PERIOD_DAYS / 4.0])
    design = fourier_design(doy, n_harmonics=1)
    # column order: [intercept, sin(k=1), cos(k=1)]
    assert design.shape == (2, 3)
    np.testing.assert_allclose(design[:, 0], 1.0)
    np.testing.assert_allclose(design[0], [1.0, 0.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(design[1], [1.0, 1.0, 0.0], atol=1e-12)


def test_fourier_design_two_harmonics_has_five_columns() -> None:
    design = fourier_design(np.array([10.0, 20.0, 30.0]), n_harmonics=2)
    assert design.shape == (3, 5)


def test_fit_logistic_recovers_known_coefficients() -> None:
    rng = np.random.default_rng(0)
    n = 20_000
    X = np.column_stack([np.ones(n), rng.normal(size=n), rng.normal(size=n)])
    true_beta = np.array([-0.3, 1.2, -0.7])
    p = 1.0 / (1.0 + np.exp(-(X @ true_beta)))
    y = rng.binomial(1, p).astype(float)

    fit = fit_logistic(X, y)

    assert fit.converged
    np.testing.assert_allclose(fit.coef, true_beta, atol=0.05)
    preds = predict_logistic(fit, X)
    assert preds.min() >= 0.0 and preds.max() <= 1.0


def test_fit_gamma_log_link_recovers_known_mean_and_shape() -> None:
    rng = np.random.default_rng(1)
    n = 20_000
    X = np.column_stack([np.ones(n), rng.normal(size=n)])
    true_beta = np.array([3.0, 0.4])  # log-mean intercept + slope
    true_shape = 5.0
    mu = np.exp(X @ true_beta)
    # numpy's gamma(shape, scale) has mean shape*scale -> scale = mu/shape
    y = rng.gamma(shape=true_shape, scale=mu / true_shape)

    fit = fit_gamma_log_link(X, y)

    assert fit.converged
    np.testing.assert_allclose(fit.coef, true_beta, atol=0.05)
    assert fit.extra["shape"] == pytest.approx(true_shape, rel=0.1)
    mean_pred = predict_gamma_mean(fit, X)
    assert np.all(mean_pred > 0)


def _daily(dates: list[date], rain: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"date": dates, "rain_mm": rain})


def test_build_occurrence_dataset_classifies_transitions_correctly() -> None:
    # dry, wet, wet, dry over 4 contiguous days -> 3 transitions:
    #   day0(dry)->day1(wet): p01 row, label wet
    #   day1(wet)->day2(wet): p11 row, label wet
    #   day2(wet)->day3(dry): p11 row, label dry
    dates = [date(2020, 1, 1) + timedelta(days=i) for i in range(4)]
    rain = [0.0, 5.0, 3.0, 0.0]
    daily = _daily(dates, rain)

    ds = build_occurrence_dataset(daily, n_harmonics=1, covariate_cols=[])

    assert ds.y01.tolist() == [1.0]
    assert sorted(ds.y11.tolist()) == [0.0, 1.0]
    assert ds.X01.shape[0] == 1
    assert ds.X11.shape[0] == 2


def test_build_occurrence_dataset_excludes_transitions_across_a_gap() -> None:
    # day0, day1 contiguous; day1 -> day5 has a 4-day gap and must be
    # dropped rather than treated as a same-day transition.
    dates = [date(2020, 1, 1), date(2020, 1, 2), date(2020, 1, 6)]
    rain = [0.0, 5.0, 0.0]
    daily = _daily(dates, rain)

    ds = build_occurrence_dataset(daily, n_harmonics=1, covariate_cols=[])

    # Only the day0(dry)->day1(wet) transition survives; the gapped
    # day1->day6 transition is excluded entirely.
    assert ds.X01.shape[0] + ds.X11.shape[0] == 1
    assert ds.y01.tolist() == [1.0]
    assert ds.X11.shape[0] == 0


def test_build_amount_dataset_keeps_only_wet_days() -> None:
    dates = [date(2020, 1, 1) + timedelta(days=i) for i in range(4)]
    rain = [0.0, 5.0, 0.05, 2.0]  # 0.05mm is below WET_THRESHOLD_MM (0.1)
    daily = _daily(dates, rain)

    X, amounts = build_amount_dataset(daily, n_harmonics=1, covariate_cols=[])

    assert sorted(amounts.tolist()) == [2.0, 5.0]
    assert X.shape[0] == 2


def test_attach_monthly_covariate_joins_by_year_month_and_drops_unmatched() -> None:
    daily = _daily(
        [date(2020, 1, 15), date(2020, 2, 15), date(2020, 3, 15)],
        [1.0, 2.0, 3.0],
    )
    climate_idx = pl.DataFrame(
        {
            "index": ["oni", "oni", "dmi"],
            "date": [date(2020, 1, 15), date(2020, 2, 15), date(2020, 1, 15)],
            "value": [0.5, -0.2, 0.1],
            "release_date": [date(2026, 1, 1)] * 3,
        }
    ).with_columns(pl.col("date").cast(pl.Date))

    joined = attach_monthly_covariate(daily, climate_idx, index_name="oni", col_name="oni")

    assert joined.height == 2  # March has no matching ONI row -> dropped
    assert set(joined["oni"].to_list()) == {0.5, -0.2}
