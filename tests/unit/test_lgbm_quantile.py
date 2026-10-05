from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from mq.forecasting.lgbm_quantile import (
    FEATURE_COLS,
    LgbmQuantileModel,
    _samples_from_quantile_grid,
    fit_lgbm_quantile_model,
    lgbm_forecast_samples,
    predict_quantiles,
)


class _FixedUniformRng:
    """Duck-typed stand-in for np.random.Generator -- returns a fixed
    array from .uniform() so interpolation can be checked exactly
    rather than statistically. Not a real Generator subtype; fine
    since tests/ isn't mypy-checked (see pyproject.toml's `packages`)."""

    def __init__(self, values: list[float]) -> None:
        self.values = np.array(values)

    def uniform(self, low: float, high: float, size: int) -> np.ndarray:
        assert size == len(self.values)
        return self.values


class _FakeLgbModel:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, features: np.ndarray) -> np.ndarray:
        return np.array([self.value])


def test_samples_from_quantile_grid_exact_interpolation() -> None:
    quantiles = {0.05: 10.0, 0.25: 20.0, 0.5: 30.0, 0.75: 40.0, 0.95: 50.0}
    rng = _FixedUniformRng([0.0, 0.15, 0.5, 1.0])
    samples = _samples_from_quantile_grid(quantiles, rng=rng, n_samples=4)  # type: ignore[arg-type]
    # lo_ext = 10 - 50*0.05 = 7.5; hi_ext = 50 + 50*0.05 = 52.5
    # u=0.15 is 0.5 of the way from 0.05 to 0.25 -> 10 + 0.5*(20-10) = 15.0
    np.testing.assert_allclose(samples, [7.5, 15.0, 30.0, 52.5])


def test_predict_quantiles_rearranges_crossing_predictions() -> None:
    # Deliberately out-of-order raw values (q=0.05 predicts HIGHER than
    # q=0.5) -- predict_quantiles must still return a monotone grid.
    models = {
        0.05: _FakeLgbModel(40.0),
        0.25: _FakeLgbModel(10.0),
        0.5: _FakeLgbModel(30.0),
        0.75: _FakeLgbModel(20.0),
        0.95: _FakeLgbModel(50.0),
    }
    model = LgbmQuantileModel(models=models)  # type: ignore[arg-type]
    quantiles = predict_quantiles(model, np.zeros(4))

    values = [quantiles[q] for q in sorted(quantiles)]
    assert values == sorted(values)
    assert sorted(values) == sorted([40.0, 10.0, 30.0, 20.0, 50.0])


def test_fit_and_predict_recovers_a_known_linear_signal() -> None:
    rng = np.random.default_rng(0)
    n = 2000
    anomaly = rng.normal(0, 100, size=n)
    oni = rng.normal(0, 1, size=n)
    dmi = rng.normal(0, 1, size=n)
    days_remaining = rng.integers(1, 90, size=n).astype(float)
    # strong, noise-free linear signal in `anomaly` only
    target = 500.0 - 1.5 * anomaly + rng.normal(0, 5, size=n)

    rows = pl.DataFrame(
        {
            "observed_to_date_anomaly_mm": anomaly,
            "oni": oni,
            "dmi": dmi,
            "days_remaining": days_remaining,
            "target_remaining_rain_mm": target,
        }
    )
    model = fit_lgbm_quantile_model(rows)

    low_anomaly_features = np.array([-200.0, 0.0, 0.0, 30.0])
    high_anomaly_features = np.array([200.0, 0.0, 0.0, 30.0])
    low_median = predict_quantiles(model, low_anomaly_features)[0.5]
    high_median = predict_quantiles(model, high_anomaly_features)[0.5]

    # target decreases with anomaly -> low anomaly should predict higher.
    assert low_median > high_median

    samples = lgbm_forecast_samples(model, low_anomaly_features, rng=rng, n_samples=500)
    assert samples.shape == (500,)
    assert set(FEATURE_COLS) == {
        "observed_to_date_anomaly_mm",
        "oni",
        "dmi",
        "days_remaining",
    }


def test_samples_cover_a_reasonable_range_around_the_median() -> None:
    quantiles = {0.05: 100.0, 0.25: 150.0, 0.5: 200.0, 0.75: 250.0, 0.95: 300.0}
    rng = np.random.default_rng(1)
    samples = _samples_from_quantile_grid(quantiles, rng=rng, n_samples=10_000)
    assert np.median(samples) == pytest.approx(200.0, abs=5.0)
    assert samples.min() > 0.0
    assert samples.max() < 400.0
