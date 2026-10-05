"""Response envelope (SPEC §9.1): every API response wraps its payload
in this shape, carrying the lineage metadata every number on the
eventual dashboard needs to be "hoverable to reveal its lineage"
(SPEC §10) — `as_of`, `data_version`, `model_version`, whether the
payload is synthetic, and the standing research-only disclaimer.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

DISCLAIMER = "Research analytics. Not investment advice."


class Meta(BaseModel):
    as_of: date | None = None
    data_version: str | None = None
    model_version: str | None = None
    spec_version: str | None = None
    generated_at: datetime
    synthetic: bool = False
    disclaimer: str = Field(default=DISCLAIMER)


class Envelope[T](BaseModel):
    data: T
    meta: Meta
