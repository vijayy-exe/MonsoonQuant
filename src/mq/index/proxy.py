"""Proxy-vs-official index error tracking (SPEC §7.2).

No official NCDEX settlement series is available to this project yet —
same V5/V12 situation documented in docs/STATUS.md (the official spot is
disseminated on ncdex.com, behind the same bot-gate as bhavcopy). This
module is ready to compare the moment an official series is available
(manually transcribed, or once live fetch is unblocked); until then
there's nothing to call it with, which is the honest state to be in
rather than fabricating a comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from mq.index.engine import IndexPath


@dataclass(frozen=True)
class ProxyErrorReport:
    n_obs: int
    mean_abs_error: float
    max_abs_error: float
    mean_pct_lpa_error: float  # abs_error / season_lpa_anchor — a scale-free cross-check
    per_date_abs_error: dict[date, float]


def proxy_error(path: IndexPath, official: dict[date, float]) -> ProxyErrorReport:
    """Compare `path`'s proxy spot values against `official`, an
    {obs_date: official_value} mapping covering at least some of
    `path.dates`. Raises ValueError if there's no overlap at all —
    silently reporting on zero observations would look like a passing
    result."""
    per_date_error = {}
    for obs_date, proxy_value in zip(path.dates, path.spot, strict=True):
        if obs_date not in official:
            continue
        per_date_error[obs_date] = abs(proxy_value - official[obs_date])

    if not per_date_error:
        raise ValueError("no overlapping dates between the proxy path and the official series")

    errors = list(per_date_error.values())
    n = len(errors)
    return ProxyErrorReport(
        n_obs=n,
        mean_abs_error=sum(errors) / n,
        max_abs_error=max(errors),
        mean_pct_lpa_error=(sum(errors) / n) / abs(path.season_lpa_anchor) * 100
        if path.season_lpa_anchor
        else float("nan"),
        per_date_abs_error=per_date_error,
    )
