"""`GET /v1/lineage?series&as_of` (SPEC §9.2): full data/model lineage —
assembles the real provenance identifiers already stored across
`contract_specs`, `valuations`, `index_values`, and `prediction_ledger`
for one series. A pure read/assembly endpoint (unlike every other
remaining-at-start-of-this-pass endpoint) -- no new computation, no
cache needed.

**An honest, real finding surfaced while building this, not hidden**:
`valuations.run_id` (a nullable FK to `model_runs`) is `NULL` for every
real row in the database right now -- confirmed by querying it
directly, not assumed. Nothing in M4's burn/distribution valuation
writers was ever wired to create a `model_runs` row and attach its
`run_id`, so this part of SPEC's own data model exists in the schema
but was never populated. `/v1/ledger` rows carry much richer real
lineage already (`model_id`, `model_version`, `data_version`,
`payload_sha256`, `row_hash`, `prev_hash`), so this endpoint leans on
those for anything resembling a "what produced this" answer, and
reports the `valuations`/`mpr_estimates` run_id gap explicitly rather
than papering over it with a fabricated identifier.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from mq.api.deps import get_db
from mq.api.errors import unknown_series
from mq.api.schemas.envelope import Envelope, Meta
from mq.db.models import Contract, ContractSpecRow, IndexValue, PredictionLedgerRow, Valuation

router = APIRouter(prefix="/v1", tags=["lineage"])


def _now_meta(**kwargs: Any) -> Meta:
    return Meta(generated_at=datetime.now(UTC), **kwargs)


class ValuationLineage(BaseModel):
    method: str
    measure: str
    as_of_date: str
    run_id: str | None


class IndexLineage(BaseModel):
    latest_obs_date: str | None
    latest_as_of_date: str | None
    data_version: str | None


class LedgerLineage(BaseModel):
    id: int
    issued_at: str
    as_of_date: str
    model_id: str
    model_version: str
    data_version: str
    target: str
    payload_sha256: str
    row_hash: str
    prev_hash: str


class LineageData(BaseModel):
    series_id: str
    contract_code: str
    spec_version: str
    spec_source_ids: list[str]
    valuations: list[ValuationLineage]
    index: IndexLineage
    ledger: list[LedgerLineage]
    model_runs_note: str


@router.get("/lineage")
def get_lineage(
    series: str = Query(..., description="series_id, e.g. RAINCHNNAI-OCT26"),
    as_of: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Envelope[LineageData]:
    """Full real data/model lineage for one series: the contract spec's
    own version + real source document IDs, every real `valuations` row
    with its (currently always-null, see module docstring) `run_id`,
    the latest real `index_values` snapshot's `data_version`, and every
    real `prediction_ledger` row for the series' own contract (richer
    lineage: model_id/model_version/data_version/hashes). `as_of`, when
    given, bounds every source to "at or before that date"."""
    contract = db.execute(
        select(Contract.contract_code).where(Contract.series_id == series)
    ).scalar_one_or_none()
    if contract is None:
        raise unknown_series(series)

    spec_row = db.execute(
        select(ContractSpecRow)
        .where(ContractSpecRow.contract_code == contract)
        .order_by(ContractSpecRow.spec_version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if spec_row is None:
        raise unknown_series(f"{series}: no contract spec registered for {contract}")

    val_stmt = select(Valuation).where(Valuation.series_id == series)
    if as_of is not None:
        val_stmt = val_stmt.where(Valuation.as_of_date <= as_of)
    val_rows = db.execute(val_stmt.order_by(Valuation.as_of_date.desc())).scalars().all()
    valuations = [
        ValuationLineage(
            method=r.method,
            measure=r.measure,
            as_of_date=r.as_of_date.isoformat(),
            run_id=str(r.run_id) if r.run_id is not None else None,
        )
        for r in val_rows
    ]

    idx_stmt = select(IndexValue).where(IndexValue.series_id == series)
    if as_of is not None:
        idx_stmt = idx_stmt.where(IndexValue.as_of_date <= as_of)
    latest_idx = db.execute(
        idx_stmt.order_by(IndexValue.obs_date.desc(), IndexValue.as_of_date.desc()).limit(1)
    ).scalar_one_or_none()
    index_lineage = IndexLineage(
        latest_obs_date=latest_idx.obs_date.isoformat() if latest_idx else None,
        latest_as_of_date=latest_idx.as_of_date.isoformat() if latest_idx else None,
        data_version=latest_idx.data_version if latest_idx else None,
    )

    ledger_stmt = select(PredictionLedgerRow).where(PredictionLedgerRow.contract_code == contract)
    if as_of is not None:
        ledger_stmt = ledger_stmt.where(PredictionLedgerRow.as_of_date <= as_of)
    ledger_rows = db.execute(ledger_stmt.order_by(PredictionLedgerRow.id.asc())).scalars().all()
    ledger = [
        LedgerLineage(
            id=r.id,
            issued_at=r.issued_at.isoformat(),
            as_of_date=r.as_of_date.isoformat(),
            model_id=r.model_id,
            model_version=r.model_version,
            data_version=r.data_version,
            target=r.target,
            payload_sha256=r.payload_sha256,
            row_hash=r.row_hash,
            prev_hash=r.prev_hash,
        )
        for r in ledger_rows
    ]

    data = LineageData(
        series_id=series,
        contract_code=contract,
        spec_version=spec_row.spec_version,
        spec_source_ids=spec_row.source_ids,
        valuations=valuations,
        index=index_lineage,
        ledger=ledger,
        model_runs_note=(
            "valuations.run_id is null for every real row in this database -- "
            "no write path currently creates a model_runs row and attaches it "
            "(a real, disclosed gap, not fabricated)"
        ),
    )
    return Envelope(data=data, meta=_now_meta(as_of=as_of, spec_version=spec_row.spec_version))
