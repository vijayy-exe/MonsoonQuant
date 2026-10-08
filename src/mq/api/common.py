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
from mq.io.asof import read_as_of
from mq.pipelines.imd import PARQUET_DIR
from mq.pricing.burn import build_burn_sample
from mq.specs.contract import ContractSpec
from mq.specs.loader import is_draft

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


def load_rain_grid(as_of: date) -> pl.DataFrame:
    """The real IMD rain grid, bounded by the as_of-aware `mq.io` layer
    (SPEC §0.4-3 -- never read data without it)."""
    return read_as_of(
        loader=lambda: pl.read_parquet(f"{PARQUET_DIR}/**/*.parquet", hive_partitioning=True),
        date_col="date",
        as_of=as_of,
    )


def official_index_values(spec: ContractSpec, rain_grid: pl.DataFrame) -> dict[int, float]:
    """The real official (2-station) index value per season, M4's own
    `build_burn_sample` reconstruction -- the hedging/cover instrument
    every risk-engine route prices or optimises against."""
    sample = build_burn_sample(spec, rain_grid, BASIS_YEARS)
    return dict(zip(sample.years, sample.payoffs, strict=True))
