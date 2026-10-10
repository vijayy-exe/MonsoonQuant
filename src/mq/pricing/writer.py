"""Persists burn-analysis and fitted-distribution output to the
`valuations` table (SPEC §6.1). Both write measure="P" — the physical,
not pricing, measure: neither has a market-price-of-risk transform
applied (that's M6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import numpy as np

from mq.db.models import Valuation
from mq.db.session import session_scope
from mq.pricing.burn import BurnStats
from mq.pricing.distribution import FittedDistribution


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


def write_valuation(
    *,
    series_id: str,
    as_of_date: date,
    method: str,
    measure: str,
    fair_value: float,
    lo90: float,
    hi90: float,
    n_paths: int,
    run_id: UUID | None = None,
) -> Valuation:
    """Writes one `valuations` row directly from an already-computed
    (fair_value, lo90, hi90) triple — for any (method, measure) that
    doesn't have its own dedicated writer above (e.g. `method="burn",
    measure="Q_wang"/"Q_esscher"` for a Wang/Esscher-reweighted price,
    or `method="conditioned", measure="P"` for M8's forecast-
    conditioned payoff distribution)."""
    with session_scope() as session:
        row = Valuation(
            series_id=series_id,
            as_of_date=as_of_date,
            method=method,
            measure=measure,
            fair_value=Decimal(str(fair_value)),
            lo90=Decimal(str(lo90)),
            hi90=Decimal(str(hi90)),
            n_paths=n_paths,
            run_id=run_id,
        )
        merged = session.merge(row)
        session.flush()
        session.refresh(merged)
        session.expunge(merged)
        return merged


def write_distribution_valuation(
    fd: FittedDistribution,
    *,
    series_id: str,
    as_of_date: date,
    n_historical_seasons: int,
    run_id: UUID | None = None,
) -> Valuation:
    """Writes one `valuations` row (method="dist") for the CV-selected
    distribution: fair_value/lo90/hi90 from its own Monte-Carlo sample
    (SPEC's P5/P95-style band, consistent with `write_burn_valuation`).
    `n_paths` records the number of *historical seasons* the fit is based
    on, not the Monte-Carlo sample size — the number that actually bounds
    how much this estimate should be trusted."""
    fair_value = float(np.mean(fd.samples))
    lo90 = float(np.quantile(fd.samples, 0.05))
    hi90 = float(np.quantile(fd.samples, 0.95))
    with session_scope() as session:
        row = Valuation(
            series_id=series_id,
            as_of_date=as_of_date,
            method="dist",
            measure="P",
            fair_value=Decimal(str(fair_value)),
            lo90=Decimal(str(lo90)),
            hi90=Decimal(str(hi90)),
            n_paths=n_historical_seasons,
            run_id=run_id,
        )
        merged = session.merge(row)
        session.flush()
        session.refresh(merged)
        session.expunge(merged)
        return merged
