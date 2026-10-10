"""Shared helpers for API routes that need a real resolved contract
spec plus real IMD rain-grid data -- the `basis`, `hedge`, and
`parametric/design` endpoints all start from exactly this (load spec,
load rain grid, build the real official index), so it's factored out
once here rather than copy-pasted per route (which is how the original
`.scratch/*_demo.py` scripts each did it, fine for one-off scripts, not
for routes that need to stay consistent)."""

from __future__ import annotations

from datetime import date

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from mq.api.errors import unknown_series
from mq.db.models import ContractSpecRow
from mq.forecasting.features import station_average_daily_series
from mq.index.lpa import DailyLPA, compute_daily_lpa
from mq.io.asof import read_as_of
from mq.pipelines.climate_idx import PARQUET_DIR as CLIMATE_IDX_PARQUET_DIR
from mq.pipelines.imd import PARQUET_DIR, REALTIME_PARQUET_DIR
from mq.pricing.burn import build_burn_sample
from mq.pricing.simulator_glm import ChainModel, attach_monthly_covariate, fit_chain_model
from mq.specs.contract import ContractSpec
from mq.specs.loader import is_draft

# LPA base period used throughout this project (M3's real CDR index,
# M11's real scenario-lab run) -- not a new constant for the API layer.
LPA_BASE_PERIOD = (1991, 2020)

# The real historical/backtest window used throughout this project
# (M4's burn analysis, M10's basis engine real run, etc.): IMD data is
# backfilled 1991-2020 plus the real-time-ingested 2023 season -- see
# docs/STATUS.md's note on extending this range. Not a new constant
# invented for the API layer, just the same window reused.
BASIS_YEARS = [*range(1991, 2021), 2023]


def load_resolved_spec(db: Session, series_id: str, contract_code: str) -> ContractSpec:
    """The real, most-recent resolved `ContractSpec` for `contract_code`,
    reconstructed directly from the `contract_specs` table's stored JSON
    (the same shape `register_contract_spec` wrote it in) -- no
    filesystem YAML read needed at request time."""
    spec_row = db.execute(
        select(ContractSpecRow)
        .where(ContractSpecRow.contract_code == contract_code)
        .order_by(ContractSpecRow.spec_version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if spec_row is None:
        raise unknown_series(f"{series_id}: no contract spec registered for {contract_code}")
    spec = ContractSpec.model_validate(spec_row.yaml)
    if is_draft(spec):
        raise unknown_series(
            f"{series_id}: contract spec is still a draft (unresolved VERIFY items)"
        )
    return spec


def _scan_historical_rain_grid_for_basis_years() -> pl.DataFrame:
    """Reads only the `year=` partitions in `BASIS_YEARS` -- a lazy scan
    with the filter on the hive partition column lets Polars prune
    unneeded files entirely rather than reading them and discarding
    rows afterward. Real, measured difference on the full post-1951
    backfill: 128.7M rows/2.4s read-everything vs. 56.2M rows/1.1s
    pruned -- and the 2.3x row-count cut matters far more downstream,
    where `compute_index`'s per-call, per-station `.filter(lat==.. &
    lon==..)` (see `mq.index.engine._station_daily_rainfall_at_cell`)
    rescans this same frame once per historical year *and* (via
    `mq.risk.basis.basis_grid`) once per candidate cell -- a real
    regression found live: extending the backfill to 1951 (for SPEC
    §7.4's statistical holdout, which intentionally does NOT use
    `BASIS_YEARS`) made every caller of this function that reconstructs
    burn/basis samples over `BASIS_YEARS` read 2.3x more data on every
    one of those repeated calls, turning `/v1/hedge` from an ~8s
    documented cost into several minutes."""
    return (
        pl.scan_parquet(f"{PARQUET_DIR}/**/*.parquet", hive_partitioning=True)
        .filter(pl.col("year").is_in(BASIS_YEARS))
        .collect()
    )


def load_rain_grid(as_of: date) -> pl.DataFrame:
    """The real IMD rain grid, bounded by the as_of-aware `mq.io` layer
    (SPEC §0.4-3 -- never read data without it) and restricted to
    `BASIS_YEARS` -- every one of this function's callers so far
    (basis/hedge/parametric/track-record/scenarios/greeks) only ever
    evaluates *complete, closed* historical seasons within that fixed
    window, so the separate real-time directory (`load_combined_
    rain_grid`, below) was never needed until a *live* forecast for the
    current, in-progress season needed it (M7's `mq.forecasting.live`).
    A caller that genuinely needs years outside `BASIS_YEARS` (e.g. a
    research script using the fuller 1951-2020 backfill) should read
    the parquet dataset directly rather than go through this function."""
    return read_as_of(
        loader=_scan_historical_rain_grid_for_basis_years,
        date_col="date",
        as_of=as_of,
    )


_RAIN_GRID_COLS = ["date", "lat", "lon", "rain_mm"]


def load_combined_rain_grid(as_of: date) -> pl.DataFrame:
    """`load_rain_grid` plus the real-time directory -- needed for
    anything touching the *current* in-progress season (M7's live
    forecasts). Each source is independently `as_of`-bounded, then
    concatenated.

    Two real, found-not-assumed issues this function exists to handle
    correctly, not silently: (1) deduping across the full historical+
    real-time concat (tens of millions of rows) cost real minutes for
    a case that can't happen -- the two sources' date ranges never
    overlap (historical ends 2023-12-31, real-time starts 2026-09-01),
    checked by assertion instead; (2) the real-time parquet itself has
    exact duplicate rows for some days (same raw_sha256, a genuine
    double-write, not a DQ07-style revision) -- deduped cheaply since
    that source alone is ~233k rows, not >=56M. Historical component is
    `BASIS_YEARS`-scoped, same reasoning and the same real regression
    `load_rain_grid` documents -- the live forecasters this feeds train
    on exactly `BASIS_YEARS` (`mq.forecasting.features.
    build_training_rows`), so nothing downstream needs pre-1991 data
    here either."""
    historical = read_as_of(
        loader=_scan_historical_rain_grid_for_basis_years,
        date_col="date",
        as_of=as_of,
    )
    realtime = read_as_of(
        loader=lambda: pl.read_parquet(
            f"{REALTIME_PARQUET_DIR}/**/*.parquet", hive_partitioning=True
        ),
        date_col="date",
        as_of=as_of,
    )
    realtime = realtime.unique(subset=_RAIN_GRID_COLS, keep="first")

    if historical.height > 0 and realtime.height > 0:
        latest_historical = str(historical["date"].max())
        earliest_realtime = str(realtime["date"].min())
        assert latest_historical < earliest_realtime, (
            f"historical ({latest_historical}) and real-time ({earliest_realtime}) rain_grid "
            "sources now overlap -- the no-dedup-across-sources assumption no longer holds"
        )
    return pl.concat([historical.select(_RAIN_GRID_COLS), realtime.select(_RAIN_GRID_COLS)]).sort(
        "date"
    )


def official_index_values(spec: ContractSpec, rain_grid: pl.DataFrame) -> dict[int, float]:
    """The real official (2-station) index value per season, M4's own
    `build_burn_sample` reconstruction -- the hedging/cover instrument
    every risk-engine route prices or optimises against."""
    sample = build_burn_sample(spec, rain_grid, BASIS_YEARS)
    return dict(zip(sample.years, sample.payoffs, strict=True))


def load_climate_idx(as_of: date) -> pl.DataFrame:
    """The real ONI/DMI series (`mq.pipelines.climate_idx`), bounded by
    the as_of-aware `mq.io` layer -- the chain model's two real
    covariates (M5.1/M5.2)."""
    return read_as_of(
        loader=lambda: pl.read_parquet(
            f"{CLIMATE_IDX_PARQUET_DIR}/**/*.parquet", hive_partitioning=True
        ),
        date_col="date",
        as_of=as_of,
    )


def fit_real_chain_model(
    spec: ContractSpec, rain_grid: pl.DataFrame, climate_idx: pl.DataFrame
) -> tuple[ChainModel, DailyLPA, float, float]:
    """The real M5.1/M5.2 chain-model fit (`fit_chain_model`), on the
    real station-averaged daily rainfall + real ONI/DMI covariates --
    the same pipeline `.scratch/scenarios_demo.py`/`greeks_demo.py` each
    ran ad hoc, factored out once here so routes don't re-derive it.
    `fit_chain_model` itself is fast (~0.1s, confirmed by timing it
    directly); the real cost is the daily-series prep (~7s, dominated by
    the monthly-covariate join) -- see the `scenarios`/`greeks` routes'
    own model-fit cache for why that cost is paid once per
    (contract_code, as_of), not once per request.

    Returns `(model, daily_lpa, mean_oni, mean_dmi)` -- the fitted model,
    the real climatological daily-LPA baseline (needed by every
    simulate/Greeks call), and the real covariates' own historical means
    (a defensible default baseline state when a caller doesn't override
    oni/dmi for a specific scenario)."""
    if not isinstance(spec.stations, list):
        raise ValueError(f"{spec.contract_code}: contract spec has no resolved stations")
    avg_series = station_average_daily_series(rain_grid, spec.stations)
    daily = attach_monthly_covariate(avg_series, climate_idx, index_name="oni", col_name="oni")
    daily = attach_monthly_covariate(daily, climate_idx, index_name="dmi", col_name="dmi")
    model = fit_chain_model(daily, n_harmonics=3, covariate_cols=["oni", "dmi"])

    # compute_daily_lpa looks up the nearest grid cell to (lat, lon) --
    # the station-averaged series isn't gridded, so it's given a single
    # synthetic (lat=0, lon=0) cell to make the lookup trivially match,
    # the same trick `.scratch/scenarios_demo.py` used.
    avg_grid = avg_series.with_columns(lat=pl.lit(0.0), lon=pl.lit(0.0))
    daily_lpa = compute_daily_lpa(
        avg_grid,
        lat=0.0,
        lon=0.0,
        base_period_start_year=LPA_BASE_PERIOD[0],
        base_period_end_year=LPA_BASE_PERIOD[1],
    )
    mean_oni = float(daily.select(pl.col("oni").mean()).item())
    mean_dmi = float(daily.select(pl.col("dmi").mean()).item())
    return model, daily_lpa, mean_oni, mean_dmi
