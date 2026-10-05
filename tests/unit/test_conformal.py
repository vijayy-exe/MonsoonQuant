from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from mq.forecasting.conformal import (
    CqrQuantileModel,
    cqr_forecast_samples,
    fit_cqr_quantile_model,
    predict_calibrated_quantiles,
)
from mq.forecasting.lgbm_quantile import LgbmQuantileModel


class _FakeBooster:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, features: np.ndarray) -> np.ndarray:
        return np.full(features.shape[0], self.value)


def test_predict_calibrated_quantiles_applies_shift_and_rearranges() -> None:
    # Raw predictions are already sorted (10,20,30,40,50), but the
    # calibration shifts deliberately invert the order -> the result
    # must still come back monotone.
    base = LgbmQuantileModel(
        models={
            0.05: _FakeBooster(10.0),  # type: ignore[dict-item]
            0.25: _FakeBooster(20.0),  # type: ignore[dict-item]
            0.5: _FakeBooster(30.0),  # type: ignore[dict-item]
            0.75: _FakeBooster(40.0),  # type: ignore[dict-item]
            0.95: _FakeBooster(50.0),  # type: ignore[dict-item]
        }
    )
    shifts = {0.05: 100.0, 0.25: 0.0, 0.5: 0.0, 0.75: 0.0, 0.95: -100.0}
    model = CqrQuantileModel(base=base, calibration_shift=shifts, n_calibration_rows=10)

    quantiles = predict_calibrated_quantiles(model, np.zeros(4))
    values = [quantiles[q] for q in sorted(quantiles)]
    assert values == sorted(values)
    # shifted raw values: [110, 20, 30, 40, -50] -> sorted: [-50,20,30,40,110]
    assert sorted(values) == [-50.0, 20.0, 30.0, 40.0, 110.0]


def test_predict_calibrated_quantiles_zero_shift_matches_base() -> None:
    base = LgbmQuantileModel(
        models={
            0.05: _FakeBooster(10.0),  # type: ignore[dict-item]
            0.25: _FakeBooster(20.0),  # type: ignore[dict-item]
            0.5: _FakeBooster(30.0),  # type: ignore[dict-item]
            0.75: _FakeBooster(40.0),  # type: ignore[dict-item]
            0.95: _FakeBooster(50.0),  # type: ignore[dict-item]
        }
    )
    shifts = {q: 0.0 for q in (0.05, 0.25, 0.5, 0.75, 0.95)}
    model = CqrQuantileModel(base=base, calibration_shift=shifts, n_calibration_rows=10)
    quantiles = predict_calibrated_quantiles(model, np.zeros(4))
    assert quantiles == {0.05: 10.0, 0.25: 20.0, 0.5: 30.0, 0.75: 40.0, 0.95: 50.0}


def _synthetic_training_rows(n_years: int = 10, rows_per_year: int = 50) -> pl.DataFrame:
    rng = np.random.default_rng(0)
    years, anomaly, oni, dmi, days_remaining, target = [], [], [], [], [], []
    for y in range(2000, 2000 + n_years):
        a = rng.normal(0, 100, size=rows_per_year)
        years.extend([y] * rows_per_year)
        anomaly.extend(a.tolist())
        oni.extend(rng.normal(0, 1, size=rows_per_year).tolist())
        dmi.extend(rng.normal(0, 1, size=rows_per_year).tolist())
        days_remaining.extend(rng.integers(1, 90, size=rows_per_year).astype(float).tolist())
        target.extend((500.0 - 1.5 * a + rng.normal(0, 5, size=rows_per_year)).tolist())
    return pl.DataFrame(
        {
            "year": years,
            "observed_to_date_anomaly_mm": anomaly,
            "oni": oni,
            "dmi": dmi,
            "days_remaining": days_remaining,
            "target_remaining_rain_mm": target,
        }
    )


def test_fit_cqr_quantile_model_end_to_end() -> None:
    rows = _synthetic_training_rows()
    model = fit_cqr_quantile_model(rows, calibration_frac=0.3, seed=1)

    assert model.n_calibration_rows > 0
    assert set(model.calibration_shift) == {0.05, 0.25, 0.5, 0.75, 0.95}

    features = np.array([0.0, 0.0, 0.0, 30.0])
    quantiles = predict_calibrated_quantiles(model, features)
    values = [quantiles[q] for q in sorted(quantiles)]
    assert values == sorted(values)

    rng = np.random.default_rng(2)
    samples = cqr_forecast_samples(model, features, rng=rng, n_samples=200)
    assert samples.shape == (200,)


def test_fit_cqr_quantile_model_raises_with_too_few_years() -> None:
    rows = _synthetic_training_rows(n_years=3)
    with pytest.raises(ValueError, match="at least 4"):
        fit_cqr_quantile_model(rows)
