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


def gate(results: list[DQCheckResult]) -> bool:
    """True if publication should proceed — no result in `results` failed."""
    return all(r.status != "fail" for r in results)


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
