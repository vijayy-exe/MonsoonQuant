"""Live (today's) forecast rows for the 4 newer forecasting-ladder
rungs (SPEC §7, M7's own stated gap): `build_training_rows`
structurally excludes the current in-progress season (it requires a
*complete* season), so none of enso_clim_v1/analog_v1/lgbm_q_v1/
lgbm_q_cqr_v1 has ever had a real live ledger row -- only a
walk-forward *backtest* (which looks back at already-*closed* seasons)
has ever exercised them.

`clim_v1` is deliberately untouched here: it has its own existing
(single-station) live-row history from M1, and "never modify ledger
rows without asking" extends to not silently changing how its *future*
rows get produced either, without a separate ask.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import polars as pl

from mq.forecasting.analog import MODEL_ID as ANALOG_MODEL_ID
from mq.forecasting.analog import MODEL_VERSION as ANALOG_MODEL_VERSION
from mq.forecasting.analog import AnalogForecast, analog_forecast
from mq.forecasting.climatology import (
    ENSO_MODEL_ID,
    ENSO_MODEL_VERSION,
    enso_conditioned_remaining_rain_forecast,
)
from mq.forecasting.conformal import MODEL_ID as CQR_MODEL_ID
from mq.forecasting.conformal import MODEL_VERSION as CQR_MODEL_VERSION
from mq.forecasting.conformal import cqr_forecast_samples, fit_cqr_quantile_model
from mq.forecasting.features import build_live_feature_row, build_training_rows
from mq.forecasting.lgbm_quantile import FEATURE_COLS as LGBM_FEATURE_COLS
from mq.forecasting.lgbm_quantile import MODEL_ID as LGBM_MODEL_ID
from mq.forecasting.lgbm_quantile import MODEL_VERSION as LGBM_MODEL_VERSION
from mq.forecasting.lgbm_quantile import (
    QUANTILE_LEVELS,
    fit_lgbm_quantile_model,
    lgbm_forecast_samples,
)
from mq.ledger.writer import ForecastToWrite
from mq.specs.contract import ContractSpec

TARGET = "remaining_rain_mm"

# Explicit canonical order both frames get `.select()`-ed into before
# `pl.concat` -- a real mismatch found directly: `build_training_rows`
# and `build_live_feature_row` each do their own `oni`/`dmi` pivot, and
# Polars doesn't guarantee the same resulting column order between two
# independently-built pivots (confirmed: "schema names differ: got
# dmi, expected oni"). `vertical_relaxed` concat supertypes mismatched
# *dtypes* in matching positions, it doesn't reorder by name.
_COMBINED_COLS = [
    "year",
    "issue_date",
    "issue_month",
    "issue_day",
    "days_remaining",
    "observed_to_date_anomaly_mm",
    "target_remaining_rain_mm",
    "oni",
    "dmi",
]


def _samples_to_quantiles(samples: np.ndarray) -> dict[str, float]:
    series = pl.Series(samples)
    out: dict[str, float] = {}
    for q in QUANTILE_LEVELS:
        value = series.quantile(q, interpolation="linear")
        assert value is not None
        out[str(q)] = float(value)
    return out


def _to_forecast(
    *,
    contract_code: str,
    model_id: str,
    model_version: str,
    data_version: str,
    as_of: date,
    samples: list[float] | np.ndarray,
    quantiles: dict[str, float],
) -> ForecastToWrite:
    arr = np.asarray(samples, dtype=float)
    return ForecastToWrite(
        contract_code=contract_code,
        model_id=model_id,
        model_version=model_version,
        data_version=data_version,
        as_of_date=as_of,
        target=TARGET,
        quantiles=quantiles,
        fair_value=Decimal(str(float(np.mean(arr)))),
        fair_value_lo90=Decimal(str(float(np.quantile(arr, 0.05)))),
        fair_value_hi90=Decimal(str(float(np.quantile(arr, 0.95)))),
    )


def _build_combined(
    spec: ContractSpec,
    rain_grid: pl.DataFrame,
    climate_idx: pl.DataFrame,
    *,
    historical_years: list[int],
    as_of: date,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, int]:
    """Shared by `build_live_forecasts` and `get_live_analog_forecast`
    so the two can't silently diverge on how the live row gets built
    or combined with history. Returns (historical, live_row, combined,
    target_year)."""
    historical = build_training_rows(spec, rain_grid, climate_idx, historical_years)
    live_row = build_live_feature_row(spec, rain_grid, climate_idx, as_of)
    target_year = int(live_row["year"][0])
    # "vertical_relaxed", not plain "vertical": the two frames are built
    # independently (one from a Python-int literal, one from a `years`
    # loop), and Polars' own int-width inference for small literals
    # doesn't always agree across the two -- confirmed directly (a real
    # Int64-vs-Int32 SchemaError on `year`), not assumed compatible.
    combined = pl.concat(
        [historical.select(_COMBINED_COLS), live_row.select(_COMBINED_COLS)],
        how="vertical_relaxed",
    )
    return historical, live_row, combined, target_year


def get_live_analog_forecast(
    spec: ContractSpec,
    rain_grid: pl.DataFrame,
    climate_idx: pl.DataFrame,
    *,
    historical_years: list[int],
    as_of: date,
    k: int = 5,
) -> AnalogForecast:
    """Just the `analog_v1` rung's own real live analog-year selection
    (SPEC §10 page 3's "analog-years table") -- cheap relative to
    `build_live_forecasts` (no LightGBM/CQR fitting), for callers that
    only need to know *which* years were used, e.g. the dashboard."""
    _historical, _live_row, combined, target_year = _build_combined(
        spec, rain_grid, climate_idx, historical_years=historical_years, as_of=as_of
    )
    return analog_forecast(combined, target_year=target_year, issue_date=as_of, k=k)


def build_live_forecasts(
    spec: ContractSpec,
    rain_grid: pl.DataFrame,
    climate_idx: pl.DataFrame,
    *,
    historical_years: list[int],
    as_of: date,
    data_version: str,
    analog_k: int = 5,
    n_samples: int = 1000,
    seed: int = 7,
) -> list[ForecastToWrite]:
    """Real live forecasts for the 4 newer rungs, as of `as_of`, using
    `historical_years` as the analog/training pool (`other` years --
    `as_of`'s own in-progress season is never part of the training
    pool, only the thing being forecast). Raises loudly rather than
    silently falling back -- e.g. too few analog years, or a real data
    gap between the season start and `as_of` -- same posture as every
    other engine in this project.

    Returns one `ForecastToWrite` per rung
    (enso_clim_v1/analog_v1/lgbm_q_v1/lgbm_q_cqr_v1); the caller writes
    them via `mq.ledger.writer.write_forecast` (idempotent per
    contract/as_of/model/version, so re-running this for the same day
    is a safe no-op)."""
    historical, live_row, combined, target_year = _build_combined(
        spec, rain_grid, climate_idx, historical_years=historical_years, as_of=as_of
    )

    forecasts: list[ForecastToWrite] = []

    enso = enso_conditioned_remaining_rain_forecast(
        combined, target_year=target_year, issue_date=as_of
    )
    forecasts.append(
        _to_forecast(
            contract_code=spec.contract_code,
            model_id=ENSO_MODEL_ID,
            model_version=ENSO_MODEL_VERSION,
            data_version=data_version,
            as_of=as_of,
            samples=enso.sample_values,
            quantiles=enso.quantiles,
        )
    )

    analog = analog_forecast(combined, target_year=target_year, issue_date=as_of, k=analog_k)
    forecasts.append(
        _to_forecast(
            contract_code=spec.contract_code,
            model_id=ANALOG_MODEL_ID,
            model_version=ANALOG_MODEL_VERSION,
            data_version=data_version,
            as_of=as_of,
            samples=analog.sample_values,
            quantiles=analog.quantiles,
        )
    )

    live_features = live_row.select(LGBM_FEATURE_COLS).to_numpy()[0]

    lgbm_model = fit_lgbm_quantile_model(historical)
    lgbm_samples = lgbm_forecast_samples(
        lgbm_model, live_features, rng=np.random.default_rng(seed), n_samples=n_samples
    )
    forecasts.append(
        _to_forecast(
            contract_code=spec.contract_code,
            model_id=LGBM_MODEL_ID,
            model_version=LGBM_MODEL_VERSION,
            data_version=data_version,
            as_of=as_of,
            samples=lgbm_samples,
            quantiles=_samples_to_quantiles(lgbm_samples),
        )
    )

    cqr_model = fit_cqr_quantile_model(historical, seed=seed)
    cqr_samples = cqr_forecast_samples(
        cqr_model, live_features, rng=np.random.default_rng(seed + 1), n_samples=n_samples
    )
    forecasts.append(
        _to_forecast(
            contract_code=spec.contract_code,
            model_id=CQR_MODEL_ID,
            model_version=CQR_MODEL_VERSION,
            data_version=data_version,
            as_of=as_of,
            samples=cqr_samples,
            quantiles=_samples_to_quantiles(cqr_samples),
        )
    )

    return forecasts


__all__ = ["build_live_forecasts", "get_live_analog_forecast"]
