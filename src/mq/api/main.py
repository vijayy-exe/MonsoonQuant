"""MonsoonQuant public API (SPEC §9) — FastAPI app.

Only a real subset of SPEC's 18 listed endpoints is wired up so far
(health, contracts, series valuation, ledger) — each one backed by
real, already-tested functions from M1-M11, not stubs. The remaining
endpoints (forecast, greeks, mpr, basis, the three heavy POSTs, track-
record, lineage) are listed in `docs/STATUS.md` as explicit remaining
work, not silently missing.
"""

from __future__ import annotations

import importlib.metadata

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mq.api.errors import MqApiError, mq_api_error_handler
from mq.api.routes import contracts, health, ledger, risk, scenarios, series

app = FastAPI(
    title="MonsoonQuant API",
    version=importlib.metadata.version("monsoonquant"),
    description=(
        "Research analytics for India's exchange-traded rainfall futures. Not investment advice."
    ),
)

# SPEC §12: "CORS restricted to the web origin" -- no web origin exists yet (M13).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.add_exception_handler(MqApiError, mq_api_error_handler)

app.include_router(health.router)
app.include_router(contracts.router)
app.include_router(series.router)
app.include_router(ledger.router)
app.include_router(risk.router)
app.include_router(scenarios.router)
