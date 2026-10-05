"""lgbm_q_v1 — LightGBM quantile regression (SPEC §7.6).

Fourth rung of the forecasting ladder: one LightGBM model per quantile
level (q = 0.05...0.95), trained on
(observed-to-date anomaly, ONI, DMI, days_remaining) ->
target_remaining_rain_mm. Monotone rearrangement (sorting the
per-quantile predictions) fixes LightGBM's known quantile-crossing
problem — independently fit per-quantile models have no built-in
guarantee that q=0.05's prediction stays below q=0.95's.

**Deliberately small hyperparameters**: the training table has
thousands of rows, but the real degrees of freedom are ~n_years — rows
from the same season are highly correlated (today's rain is close to
yesterday's), not independent draws. A handful of leaves and boosting
rounds is already meaningful capacity at that effective sample size;
anything larger risks memorizing individual seasons rather than
learning a genuine (anomaly, ONI, DMI) -> rain relationship.

**Sampling for the shared evaluation framework**: `mq.forecasting.evaluate`'s
CRPS/pinball/coverage functions all take an empirical sample array, the
same currency every other rung already reports. `lgbm_forecast_samples`
draws from the piecewise-linear distribution implied by the predicted
quantile grid via inverse-CDF sampling — a standard, simple way to turn
a quantile-regression model's output into a comparable ensemble sample.

**Native `Dataset`/`Booster` API, not `LGBMRegressor`**: the
scikit-learn-compatible wrapper requires scikit-learn to be installed
(`lightgbm.sklearn` raises at import time otherwise) — an unplanned,
much larger dependency the CLAUDE.md size-check before adding lightgbm
never covered. `lgb.train`/`Booster.predict` need only the lightgbm
package itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import lightgbm as lgb
import numpy as np
import polars as pl

FEATURE_COLS = ["observed_to_date_anomaly_mm", "oni", "dmi", "days_remaining"]

MODEL_ID = "lgbm_q_v1"
MODEL_VERSION = "0.1.0"

QUANTILE_LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]

DEFAULT_PARAMS: dict[str, Any] = {
    "num_leaves": 7,
    "min_data_in_leaf": 50,
    "learning_rate": 0.1,
    "verbosity": -1,
}
DEFAULT_NUM_BOOST_ROUND = 50


@dataclass(frozen=True)
class LgbmQuantileModel:
    models: dict[float, lgb.Booster]


def fit_lgbm_quantile_model(
    training_rows: pl.DataFrame,
    *,
    params: dict[str, Any] | None = None,
    num_boost_round: int = DEFAULT_NUM_BOOST_ROUND,
) -> LgbmQuantileModel:
    X = training_rows.select(FEATURE_COLS).to_numpy()
    y = training_rows["target_remaining_rain_mm"].to_numpy()
    merged_params = {**DEFAULT_PARAMS, **(params or {})}

    models: dict[float, lgb.Booster] = {}
    for q in QUANTILE_LEVELS:
        train_set = lgb.Dataset(X, label=y)
        booster = lgb.train(
            {**merged_params, "objective": "quantile", "alpha": q},
            train_set,
            num_boost_round=num_boost_round,
        )
        models[q] = booster
    return LgbmQuantileModel(models=models)


def predict_quantiles(model: LgbmQuantileModel, features: np.ndarray) -> dict[float, float]:
    """Monotone-rearranged (sorted) per-quantile predictions for one
    feature vector."""
    raw = {
        q: float(np.asarray(booster.predict(features.reshape(1, -1)))[0])
        for q, booster in model.models.items()
    }
    sorted_values = sorted(raw.values())
    return dict(zip(sorted(raw.keys()), sorted_values, strict=True))


def lgbm_forecast_samples(
    model: LgbmQuantileModel,
    features: np.ndarray,
    *,
    rng: np.random.Generator,
    n_samples: int = 1000,
) -> np.ndarray:
    quantiles = predict_quantiles(model, features)
    return samples_from_quantile_grid(quantiles, rng=rng, n_samples=n_samples)


def extrapolated_quantile_grid(quantiles: dict[float, float]) -> tuple[list[float], list[float]]:
    """A quantile dict extended to the open interval [0, 1] by linearly
    extrapolating past the lowest/highest fitted level using the slope
    of the two nearest interior points — a standard practical choice
    when a model's fitted quantiles don't reach all the way to 0/1.
    Also used by `mq.pricing.conditioned.quantile_map`, which needs the
    identical grid construction, not just a sample drawn from it."""
    levels = sorted(quantiles)
    if len(levels) < 2:
        raise ValueError("need at least 2 quantile levels to extrapolate a grid")
    values = [quantiles[q] for q in levels]
    lo_slope = (values[1] - values[0]) / (levels[1] - levels[0])
    hi_slope = (values[-1] - values[-2]) / (levels[-1] - levels[-2])
    lo_ext = values[0] - lo_slope * levels[0]
    hi_ext = values[-1] + hi_slope * (1.0 - levels[-1])
    return [0.0, *levels, 1.0], [lo_ext, *values, hi_ext]


def samples_from_quantile_grid(
    quantiles: dict[float, float], *, rng: np.random.Generator, n_samples: int
) -> np.ndarray:
    q_levels, q_values = extrapolated_quantile_grid(quantiles)
    u = rng.uniform(0.0, 1.0, size=n_samples)
    return np.asarray(np.interp(u, q_levels, q_values))
