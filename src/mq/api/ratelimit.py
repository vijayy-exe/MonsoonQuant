"""SPEC §9.3: "Rate limit: 60 req/min anon; API keys (hashed) for higher
limits." Only the anonymous tier is implemented here — there is no
key-issuance/validation system in this project yet, so the API-key tier
stays unimplemented, not silently skipped: see docs/STATUS.md.

A simple fixed-window counter per client IP, in-process. Good enough for
this project's real scale (a single-process research API, SPEC's own
"research analytics" framing) — a multi-worker/multi-process deployment
would need a shared store (Redis), same caveat the basis/hedge/
track-record response caches already carry.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mq.api.errors import RATE_LIMITED

_WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self, *, limit_per_min: int) -> None:
        self.limit_per_min = limit_per_min
        self._lock = threading.Lock()
        # client_ip -> (window_start_epoch_seconds, count_in_window)
        self._counts: dict[str, tuple[float, int]] = {}

    def check(self, client_ip: str) -> tuple[bool, int]:
        """Returns (allowed, remaining). Not allowed -> remaining is 0."""
        now = time.time()
        with self._lock:
            window_start, count = self._counts.get(client_ip, (now, 0))
            if now - window_start >= _WINDOW_SECONDS:
                window_start, count = now, 0
            count += 1
            self._counts[client_ip] = (window_start, count)
            if count > self.limit_per_min:
                return False, 0
            return True, self.limit_per_min - count


def make_rate_limit_middleware(
    limiter: RateLimiter,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not request.url.path.startswith("/v1"):
            return await call_next(request)

        client_ip = request.client.host if request.client is not None else "unknown"
        allowed, remaining = limiter.check(client_ip)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "type": RATE_LIMITED,
                    "title": "Rate limit exceeded",
                    "status": 429,
                    "detail": f"More than {limiter.limit_per_min} requests/min from this client.",
                    "instance": str(request.url),
                },
                media_type="application/problem+json",
                headers={"Retry-After": str(_WINDOW_SECONDS)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    return middleware
