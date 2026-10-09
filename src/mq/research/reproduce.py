"""`mq research reproduce` (SPEC §17 Principle 10: "Clean checkout ->
make reproduce -> same figures", §18 Definition of Done). Regenerates
the real, measured figures the preprint (`paper/preprint.md`) and
`docs/methods/*.md` report, by calling the exact same committed engine
functions the live API already calls -- no new pricing/risk/
forecasting math lives here, only orchestration + a JSON write.

**Honest scope, not literal-from-nothing**: this needs the real local
`data/parquet/` already backfilled (`data/` is deliberately never
committed -- see `.gitignore` -- so a bare `git clone` alone gives you
code, not data). "Clean checkout" in SPEC's principle means "the code
is deterministic and committed," not "zero setup ever" -- the data
backfill is a real, separate, slower step (documented in
`docs/STATUS.md`'s "How to resume work"), same as any real research
pipeline that depends on external data sources.

Covers: M4 (burn + distribution selection), M7 (forecasting walk-
forward backtest), M9 (hedge case study), M10 (basis grid), M11
(parametric cover case study) -- the headline quantitative claims the
preprint's Sections 4-7 report. `make bench` / `make test-golden`
cover the C++ simulator benchmark and the hand-computed golden tests
respectively -- not duplicated here.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from mq.api.common import (
    BASIS_YEARS,
    load_climate_idx,
    load_rain_grid,
    load_resolved_spec,
    official_index_values,
)
from mq.db.session import session_scope
from mq.forecasting.analog import analog_forecast
from mq.forecasting.climatology import enso_conditioned_remaining_rain_forecast
from mq.forecasting.conformal import cqr_forecast_samples, fit_cqr_quantile_model
from mq.forecasting.evaluate import climatology_baseline_forecast, walk_forward_backtest
from mq.forecasting.features import build_training_rows
from mq.forecasting.lgbm_quantile import (
    FEATURE_COLS,
    fit_lgbm_quantile_model,
    lgbm_forecast_samples,
)
from mq.pricing.burn import build_burn_sample, compute_burn_stats
from mq.pricing.selection import rolling_origin_cv, select_best_distribution
from mq.risk.basis import basis_grid, local_index_series, to_geojson
from mq.risk.cvar import minimize_cvar_hedge
from mq.risk.hedge import LotConstraints, delivery_rider_income_loss, min_variance_hedge
from mq.risk.parametric import optimize_cover
from mq.specs.contract import ContractSpec

CONTRACT_CODE = "RAINCHNNAI"
# Same real candidate location M9/M10/M11's own real runs used (M10's
# weakest-correlation cell, 13.50N 79.75E) -- not a fresh choice here.
CASE_STUDY_LAT = 13.50
CASE_STUDY_LON = 79.75
MIN_TRAIN_YEARS = 10


def _json_default(obj: object) -> object:
    if isinstance(obj, np.floating | np.integer):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"not JSON-serializable: {type(obj)}")


def _write(output_dir: Path, name: str, data: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, default=_json_default, sort_keys=True))
    return path


def reproduce_burn_distribution(
    spec: ContractSpec, rain_grid: pl.DataFrame, climate_idx: pl.DataFrame
) -> dict[str, Any]:
    """M4: real 31-season burn stats + leave-one-out CRPS distribution
    selection -- `docs/methods/burn_distribution.md`'s own figures."""
    sample = build_burn_sample(spec, rain_grid, BASIS_YEARS)
    stats = compute_burn_stats(sample)

    oni = climate_idx.filter(pl.col("index") == "oni")
    cv_results = rolling_origin_cv(
        np.array(sample.payoffs), sample.years, oni=oni, rng=np.random.default_rng(42)
    )
    best = select_best_distribution(cv_results)

    return {
        "burn": asdict(stats),
        "distribution_selection": {k: asdict(v) for k, v in cv_results.items()},
        "selected": best,
    }


def reproduce_forecasting_backtest(
    spec: ContractSpec, rain_grid: pl.DataFrame, climate_idx: pl.DataFrame
) -> dict[str, Any]:
    """M7: real 5-rung walk-forward backtest -- same protocol
    `/v1/track-record` runs live, same numbers
    `docs/methods/forecasting.md` reports."""
    rows = build_training_rows(spec, rain_grid, climate_idx, BASIS_YEARS)

    def model_enso(table: pl.DataFrame, target_year: int, issue_date: date) -> np.ndarray:
        return np.array(
            enso_conditioned_remaining_rain_forecast(
                table, target_year=target_year, issue_date=issue_date
            ).sample_values
        )

    def model_analog(table: pl.DataFrame, target_year: int, issue_date: date) -> np.ndarray:
        return np.array(
            analog_forecast(
                table, target_year=target_year, issue_date=issue_date, k=5
            ).sample_values
        )

    lgbm_cache: dict[int, Any] = {}
    cqr_cache: dict[int, Any] = {}
    rng_lgbm = np.random.default_rng(10)
    rng_cqr = np.random.default_rng(11)

    def model_lgbm(table: pl.DataFrame, target_year: int, issue_date: date) -> np.ndarray:
        target_row = table.filter(pl.col("year") == target_year)
        if target_row.height == 0:
            raise ValueError("not enough data")
        if target_year not in lgbm_cache:
            train = table.filter(pl.col("year") != target_year)
            if train["year"].n_unique() < 4:
                raise ValueError("not enough data")
            lgbm_cache[target_year] = fit_lgbm_quantile_model(train)
        features = target_row.select(FEATURE_COLS).to_numpy()[0]
        return lgbm_forecast_samples(lgbm_cache[target_year], features, rng=rng_lgbm, n_samples=500)

    def model_cqr(table: pl.DataFrame, target_year: int, issue_date: date) -> np.ndarray:
        target_row = table.filter(pl.col("year") == target_year)
        if target_row.height == 0:
            raise ValueError("not enough data")
        if target_year not in cqr_cache:
            train = table.filter(pl.col("year") != target_year)
            if train["year"].n_unique() < 4:
                raise ValueError("not enough data")
            cqr_cache[target_year] = fit_cqr_quantile_model(train, seed=target_year)
        features = target_row.select(FEATURE_COLS).to_numpy()[0]
        return cqr_forecast_samples(cqr_cache[target_year], features, rng=rng_cqr, n_samples=500)

    clim_result = walk_forward_backtest(
        rows,
        climatology_baseline_forecast,
        model_id="clim_baseline",
        min_train_years=MIN_TRAIN_YEARS,
    )
    rungs = {"clim_baseline": clim_result}
    for model_fn, model_id in [
        (model_enso, "enso_clim_v1"),
        (model_analog, "analog_v1"),
        (model_lgbm, "lgbm_q_v1"),
        (model_cqr, "lgbm_q_cqr_v1"),
    ]:
        rungs[model_id] = walk_forward_backtest(
            rows, model_fn, model_id=model_id, min_train_years=MIN_TRAIN_YEARS
        )

    return {
        "n_training_rows": rows.height,
        "n_training_years": rows["year"].n_unique(),
        "rungs": {
            k: {
                "model_id": v.model_id,
                "n_predictions": v.n_predictions,
                "mean_crps": v.mean_crps,
            }
            for k, v in rungs.items()
        },
    }


def _case_study_arrays(
    spec: ContractSpec, rain_grid: pl.DataFrame
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    official_values = official_index_values(spec, rain_grid)
    local_values = local_index_series(
        spec, rain_grid, sorted(official_values), lat=CASE_STUDY_LAT, lon=CASE_STUDY_LON
    )
    common_years = sorted(set(local_values) & set(official_values))
    local_arr = np.array([local_values[y] for y in common_years])
    index_arr = np.array([official_values[y] for y in common_years])
    return local_arr, index_arr, common_years


def reproduce_hedge_case_study(spec: ContractSpec, rain_grid: pl.DataFrame) -> dict[str, Any]:
    """M9: the real synthetic Chennai delivery-rider case study
    (`docs/methods/hedge.md`) -- min-variance + CVaR95 against the real
    official index. `max_loss=500,000` and the lot constraints below
    are `docs/methods/hedge.md`'s own stated real-run values (its own
    plain-default exposure rounds to 0 lots -- a documented finding,
    not this script's bug)."""
    local_arr, index_arr, common_years = _case_study_arrays(spec, rain_grid)
    multiplier = float(spec.multiplier_inr_per_point)
    exposure_fn = delivery_rider_income_loss(max_loss=500_000.0)
    exposure_arr = exposure_fn(local_arr - local_arr.min())
    constraints = LotConstraints(max_order_lots=20, margin_budget=100_000.0, margin_per_lot=2_000.0)

    mv = min_variance_hedge(exposure_arr, index_arr, multiplier=multiplier, constraints=constraints)
    cvar = minimize_cvar_hedge(
        exposure_arr, index_arr, multiplier=multiplier, constraints=constraints
    )

    return {
        "n_years": len(common_years),
        "location": {"lat": CASE_STUDY_LAT, "lon": CASE_STUDY_LON},
        "min_variance": asdict(mv),
        "cvar95": asdict(cvar),
    }


def reproduce_parametric_case_study(spec: ContractSpec, rain_grid: pl.DataFrame) -> dict[str, Any]:
    """M11: the real synthetic Chennai delivery-rider parametric-cover
    case study (`docs/methods/parametric.md`).

    **Real discrepancy found reproducing this, not silently copied
    over**: this exact setup (plain-default `delivery_rider_income_loss`,
    loss threshold at the empirical P75, same location/years) reproduces
    `docs/methods/parametric.md`'s stated optimized
    trigger/slope/limit/premium/payout-years *exactly* -- confirmed
    both here and by calling the live `/v1/parametric/design` endpoint
    directly. But the *basis-failure-probability* figure it reports
    (0.0 for both no-cover and optimized, not the written-up
    0.258 -> 0.032) does not match, currently, on this real data: ~84%
    of this location's 31 real loss values saturate at exactly
    `max_loss` under the default `saturation_mm=200`, so the P75
    threshold itself lands on that same saturated value, and strict
    `>` comparison (`mq.risk.parametric.basis_failure_probability`)
    never counts a tied value as "exceeding" its own threshold. Reported
    honestly below rather than overwritten with the stale written-up
    number -- see the preprint's own limitations section."""
    local_arr, index_arr, common_years = _case_study_arrays(spec, rain_grid)
    exposure_fn = delivery_rider_income_loss()
    loss_arr = exposure_fn(local_arr - local_arr.min())
    loss_threshold = float(np.quantile(loss_arr, 0.75))
    # Restricted to the index's own median-to-max (M11's real finding:
    # an unrestricted grid finds a degenerate near-always-pay cover).
    trigger_grid = list(np.linspace(float(np.median(index_arr)), float(index_arr.max()), 8))

    result = optimize_cover(
        loss_arr,
        index_arr,
        direction="wet",
        loss_threshold=loss_threshold,
        budget=50_000.0,
        loading=0.2,
        trigger_grid=trigger_grid,
        slope_grid=[1.0, 5.0, 20.0, 50.0, 100.0, 300.0],
        limit_grid=[10_000.0, 50_000.0, 200_000.0, 500_000.0],
    )
    no_cover_bfp = float(np.mean(loss_arr > loss_threshold))

    return {
        "n_years": len(common_years),
        "location": {"lat": CASE_STUDY_LAT, "lon": CASE_STUDY_LON},
        "loss_threshold": loss_threshold,
        "fraction_of_years_at_saturation_cap": float(np.mean(loss_arr == loss_arr.max())),
        "no_cover_basis_failure_probability": no_cover_bfp,
        "optimized": asdict(result.params)
        | {
            "premium": result.premium,
            "basis_failure_probability": result.basis_failure_probability,
            "converged": result.converged,
        },
        "note": (
            "basis_failure_probability reproduces as 0.0 here, not the "
            "0.258/0.032 docs/methods/parametric.md states, because "
            "most years saturate at exactly the P75 threshold under "
            "strict '>' comparison -- see this function's own docstring"
        ),
    }


def reproduce_basis_grid(spec: ContractSpec, rain_grid: pl.DataFrame) -> dict[str, Any]:
    """M10: the real ~1deg basis-risk grid around RAINCHNNAI's real
    stations (`docs/methods/basis.md`)."""
    official_values = official_index_values(spec, rain_grid)
    if not isinstance(spec.stations, list):
        raise TypeError("expected a resolved station list")
    station_lats = [s.lat for s in spec.stations]
    station_lons = [s.lon for s in spec.stations]
    cells = basis_grid(
        spec,
        rain_grid,
        BASIS_YEARS,
        official_index_values=official_values,
        lat_bounds=(min(station_lats) - 0.5, max(station_lats) + 0.5),
        lon_bounds=(min(station_lons) - 0.5, max(station_lons) + 0.5),
    )
    return {"n_cells": len(cells), "geojson": to_geojson(cells)}


def reproduce_all(output_dir: Path = Path("research/figures")) -> dict[str, Path]:
    """Regenerates every figure above from real local data, writes one
    JSON per figure to `output_dir`, and returns {figure_name: path}."""
    as_of = date.today()
    with session_scope() as session:
        spec = load_resolved_spec(session, CONTRACT_CODE, CONTRACT_CODE)
    rain_grid = load_rain_grid(as_of)
    climate_idx = load_climate_idx(as_of)

    figures = {
        "burn_distribution": reproduce_burn_distribution(spec, rain_grid, climate_idx),
        "forecasting_backtest": reproduce_forecasting_backtest(spec, rain_grid, climate_idx),
        "hedge_case_study": reproduce_hedge_case_study(spec, rain_grid),
        "parametric_case_study": reproduce_parametric_case_study(spec, rain_grid),
        "basis_grid": reproduce_basis_grid(spec, rain_grid),
    }
    return {name: _write(output_dir, name, data) for name, data in figures.items()}
