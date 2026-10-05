"""RFC 9457 problem+json errors (SPEC §9.1): stable `type` codes rather
than ad hoc error shapes per endpoint, so a client can branch on `type`
without string-matching a human-readable message.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

STALE_DATA = "mq/stale-data"
UNKNOWN_SERIES = "mq/unknown-series"
INFEASIBLE_HEDGE = "mq/infeasible-hedge"


class MqApiError(Exception):
    def __init__(self, *, type_: str, title: str, status: int, detail: str | None = None) -> None:
        self.type_ = type_
        self.title = title
        self.status = status
        self.detail = detail
        super().__init__(detail or title)


def unknown_series(series_id: str) -> MqApiError:
    return MqApiError(
        type_=UNKNOWN_SERIES,
        title="Unknown series",
        status=404,
        detail=f"No series with id {series_id!r} is registered.",
    )


def stale_data(detail: str) -> MqApiError:
    return MqApiError(type_=STALE_DATA, title="Stale data", status=503, detail=detail)


def infeasible_hedge(detail: str) -> MqApiError:
    return MqApiError(
        type_=INFEASIBLE_HEDGE, title="Infeasible hedge request", status=422, detail=detail
    )


async def mq_api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, MqApiError)  # registered only for this type; narrows for mypy
    return JSONResponse(
        status_code=exc.status,
        content={
            "type": exc.type_,
            "title": exc.title,
            "status": exc.status,
            "detail": exc.detail,
            "instance": str(request.url),
        },
        media_type="application/problem+json",
    )
