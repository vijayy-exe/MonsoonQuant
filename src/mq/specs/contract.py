"""ContractSpec model (SPEC §7.1).

Every numeric/structural field that depends on an open VERIFY question
(docs/VERIFY.md) accepts the literal sentinel `"TODO_VERIFY"` in place of
its real value, so a DRAFT spec can exist and be exercised by the rest of
the codebase before the official NCDEX documents are in hand. The loader
(`mq.specs.loader`) is what actually enforces that a spec can't be used for
real pricing while any field is still pending — see §7.1's "Loader rejects
any spec with an unresolved VERIFY field unless --allow-draft."
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TODO_VERIFY = "TODO_VERIFY"
Pending = Literal["TODO_VERIFY"]


class MonthDay(BaseModel):
    """A recurring (month, day) with no year — a contract's rainfall period
    repeats every season."""

    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)

    def __str__(self) -> str:
        return f"{self.month:02d}-{self.day:02d}"


class LPARef(BaseModel):
    """Long-period-average rainfall reference (VERIFY V4): which source
    defines it, over what base period, and where the table lives."""

    source_id: str
    base_period_start_year: int
    base_period_end_year: int
    table_object_key: str | None = None


class StationRef(BaseModel):
    station_id: str
    name: str
    lat: float
    lon: float
    grid_cell: tuple[float, float] | None = None  # nearest IMD 0.25° cell
    weight: float = 1.0


class SettlementRule(BaseModel):
    """Final settlement procedure and timing (VERIFY V9)."""

    method: str
    timing: str
    notes: str | None = None


class IndexDef(BaseModel):
    kind: (
        Literal["cumulative_rain_mm", "cumulative_deviation_pct_lpa", "cumulative_deviation_mm"]
        | Pending
    )
    aggregation: Literal["mean", "weighted_mean"] | Pending
    lpa: LPARef | Pending
    period_start: MonthDay | Pending
    period_end: MonthDay | Pending
    missing_data_rule: str  # VERIFY V10 — "TODO_VERIFY" is a valid str value


class ContractSpec(BaseModel):
    contract_code: str
    spec_version: date
    stations: list[StationRef] | Pending
    index: IndexDef
    multiplier_inr_per_point: Decimal | Pending  # VERIFY V6
    tick_size: Decimal | Pending
    lot_size: int | Pending
    max_order_lots: int | Pending | None = None
    position_limit_lots: int | Pending | None = None
    margin_pct: Decimal | Pending | None = None
    settlement: SettlementRule | Pending
    source_ids: list[str] = Field(default_factory=list)
