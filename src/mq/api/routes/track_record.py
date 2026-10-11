"""`GET /v1/track-record` (SPEC §9.2): CRPS, coverage, PIT per model —
a real, on-demand re-run of M7's own 5-rung walk-forward backtest
(`mq.forecasting.evaluate.walk_forward_backtest`), against real IMD
rainfall + real ONI/DMI covariates, not stored/stale numbers.

**Why live re-run, not a stored table**: unlike `greeks`/`scenarios`,
there's no `model_runs` row for this (M7's real backtest was reported
in `docs/methods/forecasting.md` but never persisted) -- and unlike
`basis`, re-running it is itself the point of a "track record" endpoint
(it should reflect the current real data, not a frozen snapshot).
Confirmed tractable by actually timing the real scripts this route is
built from (`.scratch/forecasting_backtest.py`, `.scratch/
lgbm_backtest.py`) before committing to this design: ~17s for the
clim/enso/analog rungs, ~29s for clim/lgbm/lgbm_cqr (clim_baseline
shared, so a combined 5-rung run is well under the sum) -- the same
order of cost as `basis`'s real ~48s, so it gets the same request-hash
cache treatment.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import polars as pl
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mq.api.common import BASIS_YEARS, load_climate_idx, load_rain_grid, load_resolved_spec
from mq.api.deps import get_db
from mq.api.schemas.envelope import Envelope, Meta
from mq.forecasting.analog import analog_forecast
from mq.forecasting.climatology import enso_conditioned_remaining_rain_forecast
from mq.forecasting.conformal import cqr_forecast_samples, fit_cqr_quantile_model
from mq.forecasting.evaluate import (
    BacktestResult,
    climatology_baseline_forecast,
    crpss,
    walk_forward_backtest,
)
from mq.forecasting.features import build_training_rows
from mq.forecasting.lgbm_quantile import (
    FEATURE_COLS,
    fit_lgbm_quantile_model,
    lgbm_forecast_samples,
)

router = APIRouter(prefix="/v1", tags=["track-record"])

# Same real walk-forward protocol M7's own backtest used
# (.scratch/forecasting_backtest.py, .scratch/lgbm_backtest.py) --
# min_train_years=10, not the function's own default of 5.
MIN_TRAIN_YEARS = 10

# Response cache by (contract_code, as_of) -- this computation's real
# cost (~40-50s for all 5 rungs) is identical for every request against
# the same contract/date, so there is no finer request-hash dimension
# to key on, unlike hedge/parametric/scenarios.
_track_record_cache: dict[tuple[str, str], dict[str, Any]] = {}


def _now_meta(**kwargs: Any) -> Meta:
    return Meta(generated_at=datetime.now(UTC), **kwargs)


class PitHistogram(BaseModel):
    bin_edges: list[float]
    counts: list[int]


class RungResult(BaseModel):
    model_id: str
    n_predictions: int
    mean_crps: float
    crpss_vs_baseline: float | None
    mean_pinball_by_q: dict[str, float]
    coverage_by_level: dict[str, float]
    pit_histogram: PitHistogram


class TrackRecordData(BaseModel):
    contract_code: str
    n_training_rows: int
    n_training_years: int
    min_train_years: int
    rungs: list[RungResult]


def _pit_histogram(pit_values: list[float]) -> PitHistogram:
    counts, edges = np.histogram(pit_values, bins=10, range=(0.0, 1.0))
    return PitHistogram(bin_edges=[float(e) for e in edges], counts=[int(c) for c in counts])


def _to_rung_result(r: BacktestResult, *, baseline_crps: float | None) -> RungResult:
    return RungResult(
        model_id=r.model_id,
        n_predictions=r.n_predictions,
        mean_crps=r.mean_crps,
        crpss_vs_baseline=crpss(r.mean_crps, baseline_crps) if baseline_crps is not None else None,
        mean_pinball_by_q={str(q): v for q, v in r.mean_pinball_by_q.items()},
        coverage_by_level={str(level): v for level, v in r.coverage_by_level.items()},
        pit_histogram=_pit_histogram(r.pit_values),
    )


@router.get("/track-record")
def get_track_record(
    contract_code: str = Query(
        default="RAINCHNNAI",
        description="RAINCHNNAI is the only contract with real walk-forward training-row "
        "support right now (RAINMUMBAI's 2026 season is closed with no forecasting-ladder "
        "history) -- see docs/STATUS.md",
    ),
    as_of: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Envelope[TrackRecordData]:
    """Real M7 walk-forward backtest, all 5 ladder rungs (clim_baseline,
    enso_clim_v1, analog_v1, lgbm_q_v1, lgbm_q_cqr_v1), against real IMD
    rainfall + real ONI/DMI. CRPSS is reported honestly -- M7's own real
    run found every newer rung underperforms climatology at n=31 seasons
    (`docs/methods/forecasting.md`), and this live re-run is expected to
    reproduce that, not a nicer-looking number. Cached by
    (contract_code, as_of)."""
    effective_as_of = as_of if as_of is not None else date.today()
    cache_key = (contract_code, effective_as_of.isoformat())
    cached = _track_record_cache.get(cache_key)
    if cached is not None:
        return Envelope(
            data=TrackRecordData.model_validate(cached), meta=_now_meta(as_of=effective_as_of)
        )

    spec = load_resolved_spec(db, contract_code, contract_code)
    rain_grid = load_rain_grid(effective_as_of)
    climate_idx = load_climate_idx(effective_as_of)
    rows = build_training_rows(spec, rain_grid, climate_idx, BASIS_YEARS)
    # Neither is touched again below -- the 5-rung walk-forward backtest
    # (the memory/CPU-heavy part: up to 21 LightGBM + 21 CQR models held
    # simultaneously in lgbm_cache/cqr_cache) only ever operates on
    # `rows`. Dropping the real rain_grid (56M rows even after the
    # BASIS_YEARS partition-pruning fix) and climate_idx here frees that
    # memory before the heavy part starts, instead of holding it
    # uselessly for the whole function's lifetime -- this route has
    # crashed the dev server under memory pressure more than once.
    del rain_grid, climate_idx

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

    # Per-target-year model caches -- walk_forward_backtest calls
    # model_fn once per (year, issue_date) row, but a single LightGBM/
    # CQR model per left-out year is all that's needed (same real
    # pattern .scratch/lgbm_backtest.py used, not refit per issue_date).
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
    rung_results = [clim_result]
    for model_fn, model_id in [
        (model_enso, "enso_clim_v1"),
        (model_analog, "analog_v1"),
        (model_lgbm, "lgbm_q_v1"),
        (model_cqr, "lgbm_q_cqr_v1"),
    ]:
        rung_results.append(
            walk_forward_backtest(
                rows, model_fn, model_id=model_id, min_train_years=MIN_TRAIN_YEARS
            )
        )

    data = TrackRecordData(
        contract_code=contract_code,
        n_training_rows=rows.height,
        n_training_years=rows["year"].n_unique(),
        min_train_years=MIN_TRAIN_YEARS,
        rungs=[
            _to_rung_result(
                r, baseline_crps=clim_result.mean_crps if r.model_id != "clim_baseline" else None
            )
            for r in rung_results
        ],
    )
    _track_record_cache[cache_key] = data.model_dump(mode="json")
    return Envelope(data=data, meta=_now_meta(as_of=effective_as_of))
