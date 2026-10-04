"""Data-quality gate (SPEC §8.2). This module implements DQ01-DQ04 — the
ingestion-time checks shared by every pipeline. DQ05-DQ10 (market-data
specific) are added in M2.

Gate rule: any `fail` blocks publication for that day/dataset; callers
should check `gate(results)` before writing valuations or ledger rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

import polars as pl

from mq.db.models import DQResult as DQResultRow
from mq.db.session import session_scope

Severity = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class DQCheckResult:
    check_id: str
    dataset: str
    status: Severity
    details: dict[str, Any] = field(default_factory=dict)


def dq01_missing_dates(
    df: pl.DataFrame,
    *,
    date_col: str,
    dataset: str,
    expected_start: date,
    expected_end: date,
) -> DQCheckResult:
    """Fail if any calendar date in [expected_start, expected_end] is absent
    from `df[date_col]`."""
    present = set(df[date_col].unique().to_list())
    expected = set()
    d = expected_start
    while d <= expected_end:
        expected.add(d)
        d += timedelta(days=1)
    missing = sorted(expected - present)
    status: Severity = "fail" if missing else "pass"
    return DQCheckResult(
        check_id="DQ01",
        dataset=dataset,
        status=status,
        details={
            "missing_dates": [m.isoformat() for m in missing[:20]],
            "missing_count": len(missing),
        },
    )


def dq02_duplicate_keys(df: pl.DataFrame, *, key_cols: list[str], dataset: str) -> DQCheckResult:
    """Fail if any combination of `key_cols` repeats."""
    dup_count = df.height - df.unique(subset=key_cols).height
    status: Severity = "fail" if dup_count > 0 else "pass"
    return DQCheckResult(
        check_id="DQ02", dataset=dataset, status=status, details={"duplicate_count": dup_count}
    )


def dq03_value_range(
    df: pl.DataFrame,
    *,
    value_col: str,
    dataset: str,
    lo: float = 0.0,
    hi: float = 1000.0,
) -> DQCheckResult:
    """Fail if any value in `value_col` falls outside [lo, hi] — SPEC's
    default is the rain_mm/day bound (0, 1000mm)."""
    bad = df.filter((pl.col(value_col) < lo) | (pl.col(value_col) > hi))
    status: Severity = "fail" if bad.height > 0 else "pass"
    return DQCheckResult(
        check_id="DQ03",
        dataset=dataset,
        status=status,
        details={"out_of_range_count": bad.height, "lo": lo, "hi": hi},
    )


def dq04_schema_drift(
    df: pl.DataFrame,
    *,
    expected_schema: dict[str, pl.DataType],
    dataset: str,
) -> DQCheckResult:
    """Fail if `df`'s schema has drifted from `expected_schema` — missing
    columns or a changed dtype. Extra columns are reported but don't fail
    (additive drift is lower-risk than a column disappearing or changing
    type under callers that assume the old schema)."""
    actual = dict(df.schema)
    missing_cols = [c for c in expected_schema if c not in actual]
    extra_cols = [c for c in actual if c not in expected_schema]
    type_mismatches = {
        c: (str(actual[c]), str(expected_schema[c]))
        for c in expected_schema
        if c in actual and actual[c] != expected_schema[c]
    }
    status: Severity = "fail" if (missing_cols or type_mismatches) else "pass"
    return DQCheckResult(
        check_id="DQ04",
        dataset=dataset,
        status=status,
        details={
            "missing_columns": missing_cols,
            "extra_columns": extra_cols,
            "type_mismatches": type_mismatches,
        },
    )


def dq05_stale_market_data(
    df: pl.DataFrame,
    *,
    date_col: str,
    dataset: str,
    as_of: date,
    max_stale_days: int = 2,
) -> DQCheckResult:
    """Warn if the most recent date in `df` is more than `max_stale_days`
    behind `as_of`."""
    if df.is_empty():
        return DQCheckResult(
            check_id="DQ05", dataset=dataset, status="warn", details={"reason": "no rows"}
        )
    latest_value = df[date_col].max()
    assert isinstance(latest_value, date)
    latest = latest_value
    staleness_days = (as_of - latest).days
    status: Severity = "warn" if staleness_days > max_stale_days else "pass"
    return DQCheckResult(
        check_id="DQ05",
        dataset=dataset,
        status=status,
        details={
            "latest_date": str(latest),
            "as_of": as_of.isoformat(),
            "staleness_days": staleness_days,
        },
    )


def dq06_unknown_contract_code(
    df: pl.DataFrame, *, code_col: str, dataset: str, known_codes: set[str]
) -> DQCheckResult:
    """Warn if `df[code_col]` contains a contract code outside `known_codes`."""
    unknown = df.filter(~pl.col(code_col).is_in(list(known_codes)))[code_col].unique().to_list()
    status: Severity = "warn" if unknown else "pass"
    return DQCheckResult(
        check_id="DQ06", dataset=dataset, status=status, details={"unknown_codes": unknown}
    )


def dq07_raw_hash_revision(
    *,
    dataset: str,
    series_id: str,
    trade_date: date,
    new_sha256: str,
    previous_sha256: str | None,
) -> DQCheckResult:
    """Warn when an already-ingested (series_id, trade_date)'s raw file hash
    has changed — a silent revision the pipeline must not hide."""
    if previous_sha256 is None or previous_sha256 == new_sha256:
        return DQCheckResult(check_id="DQ07", dataset=dataset, status="pass", details={})
    return DQCheckResult(
        check_id="DQ07",
        dataset=dataset,
        status="warn",
        details={
            "series_id": series_id,
            "trade_date": trade_date.isoformat(),
            "previous_sha256": previous_sha256,
            "new_sha256": new_sha256,
        },
    )


def dq10_settle_outside_price_band(
    df: pl.DataFrame,
    *,
    settle_col: str,
    prev_settle_col: str,
    dataset: str,
    initial_slab_pct: float = 6.0,
) -> DQCheckResult:
    """Warn if a settle price moves outside the DPL initial-slab band versus
    the previous settle (VERIFY V7: RAINCHNNAI/RAINMUMBAI initial slab 6%).

    Percentage bands are a crude approximation near a zero/negative base —
    CDR settle values are deviations and can cross zero, unlike a normal
    commodity price. This is a DQ *signal*, not a replication of NCDEX's
    own (undocumented) near-zero band handling."""
    band_width = pl.col(prev_settle_col).abs() * (initial_slab_pct / 100)
    band = df.with_columns(
        (pl.col(prev_settle_col) + band_width).alias("_hi"),
        (pl.col(prev_settle_col) - band_width).alias("_lo"),
    )
    breaches = band.filter(
        (pl.col(settle_col) > pl.col("_hi")) | (pl.col(settle_col) < pl.col("_lo"))
    )
    status: Severity = "warn" if breaches.height > 0 else "pass"
    return DQCheckResult(
        check_id="DQ10", dataset=dataset, status=status, details={"breach_count": breaches.height}
    )


def gate(results: list[DQCheckResult]) -> bool:
    """True if publication should proceed — no result in `results` failed."""
    return all(r.status != "fail" for r in results)


class DQGateFailedError(RuntimeError):
    """Raised when a DQ check fails for an ingested dataset — per SPEC
    §8.2, this must block publication."""

    def __init__(self, failures: list[DQCheckResult]):
        self.failures = failures
        summary = "; ".join(f"{r.check_id}={r.details}" for r in failures)
        super().__init__(f"DQ gate failed, publication blocked: {summary}")


def persist_results(results: list[DQCheckResult], *, run_at: datetime | None = None) -> None:
    """Write `results` to the `dq_results` table (SPEC §6.1)."""
    run_at = run_at or datetime.now(UTC)
    with session_scope() as session:
        for r in results:
            session.add(
                DQResultRow(
                    check_id=r.check_id,
                    dataset=r.dataset,
                    run_at=run_at,
                    status=r.status,
                    details=r.details,
                )
            )
