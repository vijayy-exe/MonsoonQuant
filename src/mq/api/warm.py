"""Pre-warms the API's in-memory, per-process response caches
(`_basis_cache`/`_model_cache`/`_track_record_cache`, one per route
module -- see each route's own module docstring for why they aren't
shared) by hitting every expensive, cacheable endpoint with the exact
default parameters the dashboard itself uses on first visit.

These caches live in the running uvicorn *process*'s memory, not a
shared store -- there is no way to warm them except real HTTP requests
against that specific running server, which is what this module does
(a direct Python function call from a separate CLI process would only
populate a cache in that throwaway process, never the live server's).
Every route-level cache resets on each server restart; this is the
real-world situation this module exists for -- a dev server that gets
restarted under memory pressure (or a real deploy's own restart) pays
every expensive cold-cache cost again, live, on whichever visitor
happens to load that page first, unless something warms it first."""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

REAL_SERIES = [
    "RAINCHNNAI-OCT26",
    "RAINCHNNAI-NOV26",
    "RAINCHNNAI-DEC26",
    "RAINMUMBAI-JUN26",
    "RAINMUMBAI-JUL26",
    "RAINMUMBAI-AUG26",
    "RAINMUMBAI-SEP26",
]
REAL_CONTRACTS = ["RAINCHNNAI", "RAINMUMBAI"]

# Per-series endpoints a dashboard page load actually triggers --
# basis/greeks are the genuinely expensive ones (cold: tens of seconds
# to low minutes); the rest are cheap DB reads, warmed anyway so every
# page's first real visit is uniformly fast, not just the slow ones.
_SERIES_PATHS = ["basis", "greeks", "valuations/compare", "mpr", "forecast", "quotes", "index"]


@dataclass(frozen=True)
class WarmResult:
    label: str
    url: str
    status_code: int | None
    elapsed_s: float
    error: str | None = None


def _warm_one(label: str, url: str, *, timeout_s: float) -> WarmResult:
    start = time.monotonic()
    try:
        resp = requests.get(url, timeout=timeout_s)
        return WarmResult(
            label=label, url=url, status_code=resp.status_code, elapsed_s=time.monotonic() - start
        )
    except requests.RequestException as exc:
        return WarmResult(
            label=label,
            url=url,
            status_code=None,
            elapsed_s=time.monotonic() - start,
            error=str(exc),
        )


def warm_cache(
    *, base_url: str = "http://127.0.0.1:8000", timeout_s: float = 180.0
) -> list[WarmResult]:
    """Hits every expensive, cacheable GET endpoint for every real
    series/contract, in dependency order (cheapest/most-likely-already-
    warm first isn't required here -- each call is independent). Safe
    to re-run: every call is idempotent (a cache hit just returns
    fast)."""
    results: list[WarmResult] = []
    for contract in REAL_CONTRACTS:
        results.append(
            _warm_one(
                f"track-record:{contract}",
                f"{base_url}/v1/track-record?contract_code={contract}",
                timeout_s=timeout_s,
            )
        )
    for series_id in REAL_SERIES:
        for path in _SERIES_PATHS:
            results.append(
                _warm_one(
                    f"{path}:{series_id}",
                    f"{base_url}/v1/series/{series_id}/{path}",
                    timeout_s=timeout_s,
                )
            )
    return results
