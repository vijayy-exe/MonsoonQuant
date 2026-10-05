"""Shared feature-building step for both simulator backends
(`mq.pricing.simulator_ref`'s NumPy loop and `mq.pricing.simulator`'s
C++ core): turns a `SimRequest`'s (start_date, n_days, covariates) into
the per-day p01/p11/mean_amt/lpa_mm arrays each simulator's inner loop
actually consumes. Factored out once so the two backends can never
silently drift apart on how a day's features are computed — they share
this function, not a copy of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from mq.index.lpa import DailyLPA, daily_lpa_lookup
from mq.pricing.simulator_glm import (
    ChainModel,
    fourier_design,
    predict_gamma_mean,
    predict_logistic,
)


@dataclass(frozen=True)
class DailyArrays:
    p01: np.ndarray
    p11: np.ndarray
    mean_amt: np.ndarray
    lpa_mm: np.ndarray


def build_daily_arrays(
    model: ChainModel,
    daily_lpa: DailyLPA,
    *,
    start_date: date,
    n_days: int,
    covariates: list[float],
) -> DailyArrays:
    if len(covariates) != len(model.covariate_cols):
        raise ValueError(
            f"request supplies {len(covariates)} covariate value(s), "
            f"model expects {len(model.covariate_cols)} ({model.covariate_cols})"
        )
    dates = [start_date + timedelta(days=t) for t in range(n_days)]
    doy = np.array([dt.timetuple().tm_yday for dt in dates], dtype=float)

    lpa_by_day = daily_lpa_lookup(daily_lpa)
    try:
        lpa_mm = np.array([lpa_by_day[(dt.month, dt.day)] for dt in dates])
    except KeyError as exc:
        raise ValueError(f"no LPA value for calendar day {exc.args[0]}") from exc

    cov = (
        np.tile(np.asarray(covariates, dtype=float), (n_days, 1))
        if covariates
        else np.zeros((n_days, 0))
    )
    design = np.concatenate([fourier_design(doy, n_harmonics=model.n_harmonics), cov], axis=1)
    return DailyArrays(
        p01=predict_logistic(model.occurrence_01, design),
        p11=predict_logistic(model.occurrence_11, design),
        mean_amt=predict_gamma_mean(model.amount, design),
        lpa_mm=lpa_mm,
    )
