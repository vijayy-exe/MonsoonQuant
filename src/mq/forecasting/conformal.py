"""lgbm_q_cqr_v1 — conformalized quantile regression (SPEC §7.6).

Fifth rung: calibrates `lgbm_q_v1`'s per-quantile predictions via
split-conformal prediction, aimed directly at the systematic
under-coverage `analog_v1` showed in the real walk-forward backtest
(`docs/methods/forecasting.md`) — small-sample empirical forecasters
can be miscalibrated in a consistent, correctable direction, and that's
exactly what conformal calibration fixes.

Standard split-conformal quantile calibration (the quantile-regression
analogue of Romano, Patterson & Candès 2019's CQR, applied per quantile
level rather than only to one interval's two endpoints — a single fixed
shift is computed for *every* level in `QUANTILE_LEVELS`, so the whole
calibrated grid stays usable for CRPS/pinball/PIT the same way every
other rung's output already is): hold out a calibration fold of whole
*seasons* (never split a season across the fit/calibration divide, same
posture SPEC's walk-forward CV requires at the outer level), compute
each quantile model's signed residual `y - qhat_q(x)` on that fold, and
shift every future q-prediction by the empirical q-quantile of those
residuals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from mq.forecasting.lgbm_quantile import (
    FEATURE_COLS,
    QUANTILE_LEVELS,
    LgbmQuantileModel,
    fit_lgbm_quantile_model,
    predict_quantiles,
    samples_from_quantile_grid,
)

MODEL_ID = "lgbm_q_cqr_v1"
MODEL_VERSION = "0.1.0"


@dataclass(frozen=True)
class CqrQuantileModel:
    base: LgbmQuantileModel
    calibration_shift: dict[float, float]
    n_calibration_rows: int


def fit_cqr_quantile_model(
    training_rows: pl.DataFrame,
    *,
    calibration_frac: float = 0.3,
    seed: int = 0,
    params: dict[str, Any] | None = None,
    num_boost_round: int | None = None,
) -> CqrQuantileModel:
    """Splits `training_rows` by YEAR (never mid-season) into a proper-
    training set and a calibration set, fits `lgbm_q_v1` on the former,
    and computes the per-quantile calibration shift from the latter."""
    years = sorted(training_rows["year"].unique().to_list())
    if len(years) < 4:
        raise ValueError(
            f"need at least 4 distinct years to split proper-train/calibration, got {len(years)}"
        )
    rng = np.random.default_rng(seed)
    n_cal_years = max(1, round(len(years) * calibration_frac))
    cal_years = set(rng.choice(years, size=n_cal_years, replace=False).tolist())
    if len(cal_years) == len(years):
        cal_years = set(list(cal_years)[:-1])  # always leave at least one proper-train year

    proper_train = training_rows.filter(~pl.col("year").is_in(cal_years))
    calibration = training_rows.filter(pl.col("year").is_in(cal_years))
    if calibration.height == 0 or proper_train.height == 0:
        raise ValueError("proper-train/calibration split produced an empty fold")

    fit_kwargs: dict[str, Any] = {"params": params}
    if num_boost_round is not None:
        fit_kwargs["num_boost_round"] = num_boost_round
    base = fit_lgbm_quantile_model(proper_train, **fit_kwargs)

    cal_X = calibration.select(FEATURE_COLS).to_numpy()
    cal_y = calibration["target_remaining_rain_mm"].to_numpy()

    shifts: dict[float, float] = {}
    for q, booster in base.models.items():
        preds = np.asarray(booster.predict(cal_X))
        residuals = cal_y - preds
        shifts[q] = float(np.quantile(residuals, q))

    return CqrQuantileModel(
        base=base, calibration_shift=shifts, n_calibration_rows=calibration.height
    )


def predict_calibrated_quantiles(
    model: CqrQuantileModel, features: np.ndarray
) -> dict[float, float]:
    """Raw per-quantile predictions, each shifted by its calibration
    correction, then monotone-rearranged (sorted) — the shift can
    itself reintroduce crossing even if the base model's raw grid
    happened to be sorted, since each quantile's shift is independent."""
    raw = predict_quantiles(model.base, features)
    shifted = {q: value + model.calibration_shift[q] for q, value in raw.items()}
    sorted_values = sorted(shifted.values())
    return dict(zip(sorted(shifted.keys()), sorted_values, strict=True))


def cqr_forecast_samples(
    model: CqrQuantileModel,
    features: np.ndarray,
    *,
    rng: np.random.Generator,
    n_samples: int = 1000,
) -> np.ndarray:
    quantiles = predict_calibrated_quantiles(model, features)
    return samples_from_quantile_grid(quantiles, rng=rng, n_samples=n_samples)


__all__ = [
    "MODEL_ID",
    "MODEL_VERSION",
    "QUANTILE_LEVELS",
    "CqrQuantileModel",
    "cqr_forecast_samples",
    "fit_cqr_quantile_model",
    "predict_calibrated_quantiles",
]
