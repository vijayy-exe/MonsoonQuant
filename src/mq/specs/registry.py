"""Registers a resolved ContractSpec into the DB (SPEC §6.1): the
`contract_specs` row (the YAML itself, versioned) and one `contracts` row
per listed series from the contract's own launch calendar.

Expiry/last-trading-day uses a weekends-only business-day approximation —
no NCDEX trading-holiday calendar is ingested yet, so a holiday landing on
what this computes as the last trading day would be off by one day. Flagged
here rather than silently assumed exact.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from mq.db.models import Contract
from mq.db.models import ContractSpecRow as ContractSpecRowModel
from mq.db.session import session_scope
from mq.specs.contract import ContractSpec, MonthDay
from mq.specs.loader import is_draft


def _last_weekday_of_month(year: int, month: int) -> date:
    """Approximates "last trading day = business day immediately preceding
    the last calendar day of the month" — weekends-only, no holiday
    calendar."""
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d


@dataclass(frozen=True)
class ListedSeries:
    series_id: str
    expiry_year: int
    expiry_month: int

    @property
    def last_trading_day(self) -> date:
        return _last_weekday_of_month(self.expiry_year, self.expiry_month)

    @property
    def due_day(self) -> date:
        """Due/expiry day = the calendar day immediately following the
        last trading day (not necessarily a weekday itself)."""
        return self.last_trading_day + timedelta(days=1)


def series_id_for(contract_code: str, year: int, month: int) -> str:
    return f"{contract_code}-{date(year, month, 1).strftime('%b%y').upper()}"


def register_contract_spec(spec: ContractSpec, *, source_ids: list[str] | None = None) -> None:
    """Upsert the `contract_specs` row: (contract_code, spec_version) -> the
    full resolved spec as JSON."""
    with session_scope() as session:
        session.merge(
            ContractSpecRowModel(
                contract_code=spec.contract_code,
                spec_version=spec.spec_version.isoformat(),
                yaml=spec.model_dump(mode="json"),
                source_ids=source_ids if source_ids is not None else spec.source_ids,
            )
        )


def register_listed_series(
    spec: ContractSpec,
    *,
    expiry_months: list[tuple[int, int]],
    as_of: date,
) -> list[Contract]:
    """Upsert one `contracts` row per (year, month) in `expiry_months`.

    All listed series of a CDR contract share the same underlying index
    window (`period_start`/`period_end` from the spec) — per the official
    product note, the cumulative deviation never resets between a
    season's months, only each series' own expiry date differs. Status is
    derived from `as_of` vs. each series' computed due day: "expired" if
    already past, otherwise "active" (this project doesn't model a
    not-yet-launched state since both real contracts are already live)."""
    if is_draft(spec):
        raise ValueError(f"cannot register listed series for a draft spec: {spec.contract_code}")
    if not isinstance(spec.index.period_start, MonthDay) or not isinstance(
        spec.index.period_end, MonthDay
    ):
        raise TypeError("expected a resolved period_start/period_end")

    rows: list[Contract] = []
    with session_scope() as session:
        for year, month in expiry_months:
            series = ListedSeries(
                series_id=series_id_for(spec.contract_code, year, month),
                expiry_year=year,
                expiry_month=month,
            )
            # The season's period_start/period_end live in the same
            # calendar year as the expiry for both real contracts (no
            # year-wrapping season), so period_start/end share that year.
            period_start = date(year, spec.index.period_start.month, spec.index.period_start.day)
            period_end = date(year, spec.index.period_end.month, spec.index.period_end.day)
            status = "expired" if series.due_day < as_of else "active"

            row = Contract(
                series_id=series.series_id,
                contract_code=spec.contract_code,
                spec_version=spec.spec_version.isoformat(),
                period_start=period_start,
                period_end=period_end,
                expiry=series.due_day,
                status=status,
            )
            merged = session.merge(row)
            session.flush()
            session.refresh(merged)
            session.expunge(merged)
            rows.append(merged)
    return rows
