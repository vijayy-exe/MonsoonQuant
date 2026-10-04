"""The as_of-aware data access layer.

Hard rule (SPEC §0.4-3): no look-ahead. Every feature, fit and forecast is
computed with data available at the issue timestamp — enforced here, not by
discipline. Pipelines, engines and research code must bound every dataframe
through this module rather than filtering dates themselves.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import polars as pl


class AsOfViolationError(RuntimeError):
    """Raised when data beyond an information cutoff reached an engine."""


def enforce_as_of(df: pl.DataFrame, date_col: str, as_of: date) -> pl.DataFrame:
    """Return only the rows of `df` observable as of `as_of`.

    This is the one sanctioned way to bound a dataframe by an information
    cutoff — call it immediately after any load, before the data reaches an
    engine or a model.
    """
    if date_col not in df.columns:
        raise KeyError(f"{date_col!r} not in dataframe columns {df.columns}")
    return df.filter(pl.col(date_col) <= as_of)


def assert_no_lookahead(df: pl.DataFrame, date_col: str, as_of: date) -> None:
    """Raise AsOfViolationError if `df` contains any row beyond `as_of`.

    Call this at the boundary of every engine entry point so that leakage
    introduced anywhere upstream (a forgotten filter, a manual load in a
    notebook) is caught by code, not review.
    """
    if date_col not in df.columns:
        raise KeyError(f"{date_col!r} not in dataframe columns {df.columns}")
    if df.is_empty():
        return
    max_date = df.select(pl.col(date_col).max()).item()
    if max_date is not None and max_date > as_of:
        raise AsOfViolationError(
            f"look-ahead violation: {date_col}={max_date} exceeds as_of={as_of}"
        )


def read_as_of(
    loader: Callable[[], pl.DataFrame],
    *,
    date_col: str,
    as_of: date,
) -> pl.DataFrame:
    """Load a dataframe via `loader`, then filter and verify it against `as_of`.

    This is the shape every concrete reader in `mq.pipelines`/`mq.index`/etc.
    should funnel through: `loader` does the actual I/O (parquet, DB, API),
    this function guarantees the as_of boundary is never silently crossed.
    """
    raw = loader()
    bounded = enforce_as_of(raw, date_col=date_col, as_of=as_of)
    assert_no_lookahead(bounded, date_col=date_col, as_of=as_of)
    return bounded
