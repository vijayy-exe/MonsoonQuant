"""Persists a calibrated market-price-of-risk estimate to the
`mpr_estimates` table (SPEC §6.1). Mirrors `mq.pricing.writer`'s
merge/flush/refresh/expunge pattern."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from mq.db.models import MPREstimate
from mq.db.session import session_scope
from mq.mpr.calibrate import CalibrationResult
from mq.mpr.uncertainty import BootstrapResult


def write_mpr_estimate(
    result: CalibrationResult,
    *,
    series_id: str,
    as_of_date: date,
    transform: str,
    days_to_expiry: int,
    volume: int,
    open_interest: int,
    bootstrap: BootstrapResult | None = None,
    run_id: UUID | None = None,
) -> MPREstimate:
    """`transform` is `"wang"` or `"esscher"`. `bootstrap`, when given,
    supplies `ci_lo`/`ci_hi` (its 90% band) and `method_ci="bootstrap"`;
    without it, no CI is recorded rather than a fabricated one."""
    with session_scope() as session:
        row = MPREstimate(
            series_id=series_id,
            as_of_date=as_of_date,
            transform=transform,
            lambda_=Decimal(str(result.param)),
            ci_lo=Decimal(str(bootstrap.lo90)) if bootstrap is not None else None,
            ci_hi=Decimal(str(bootstrap.hi90)) if bootstrap is not None else None,
            method_ci="bootstrap" if bootstrap is not None else None,
            days_to_expiry=days_to_expiry,
            volume=volume,
            open_interest=open_interest,
            n_obs=1,
            run_id=run_id,
        )
        merged = session.merge(row)
        session.flush()
        session.refresh(merged)
        session.expunge(merged)
        return merged
