"""Persists burn-analysis output to the `valuations` table (SPEC §6.1,
method="burn", measure="P" — the physical, not pricing, measure: burn
analysis has no market-price-of-risk transform applied)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from mq.db.models import Valuation
from mq.db.session import session_scope
from mq.pricing.burn import BurnStats


def write_burn_valuation(
    stats: BurnStats,
    *,
    series_id: str,
    as_of_date: date,
    run_id: UUID | None = None,
) -> Valuation:
    """Writes one `valuations` row: fair_value = burn mean, lo90/hi90 =
    P5/P95 of the historical sample (a burn-analysis band, not a formal
    90% confidence interval — SPEC's own P5...P95 burn output, reused as
    the closest available uncertainty band at this stage)."""
    with session_scope() as session:
        row = Valuation(
            series_id=series_id,
            as_of_date=as_of_date,
            method="burn",
            measure="P",
            fair_value=Decimal(str(stats.mean)),
            lo90=Decimal(str(stats.p5)),
            hi90=Decimal(str(stats.p95)),
            n_paths=stats.n,
            run_id=run_id,
        )
        merged = session.merge(row)
        session.flush()
        session.refresh(merged)
        session.expunge(merged)
        return merged
