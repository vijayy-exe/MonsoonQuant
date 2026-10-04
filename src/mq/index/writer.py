"""Persists an `IndexPath` (mq.index.engine.compute_index output) to the
`index_values` table (SPEC §6.1) — one row per (series_id, obs_date,
as_of_date).

A single CDR index path is shared by every listed series still open
during its window (SPEC §7.7's product-note note that the cumulative
deviation never resets between a season's months), so the same proxy
values are written once per active series_id, not recomputed per series.
"""

from __future__ import annotations

from decimal import Decimal

from mq.db.models import IndexValue
from mq.db.session import session_scope
from mq.index.engine import IndexPath


def write_index_values(
    path: IndexPath, *, series_ids: list[str], data_version: str
) -> list[IndexValue]:
    """Write one `index_values` row per (series_id, obs_date) in `path`.
    `official_value`/`abs_error`/`pct_lpa_error` are left null — no
    official settlement series is available yet (VERIFY V5/V12; see
    docs/STATUS.md). Returns the written rows (detached, safe to read
    after this function returns)."""
    rows: list[IndexValue] = []
    with session_scope() as session:
        for series_id in series_ids:
            for obs_date, spot_value in zip(path.dates, path.spot, strict=True):
                row = IndexValue(
                    series_id=series_id,
                    obs_date=obs_date,
                    as_of_date=path.as_of,
                    proxy_value=Decimal(str(spot_value)),
                    official_value=None,
                    abs_error=None,
                    pct_lpa_error=None,
                    data_version=data_version,
                )
                merged = session.merge(row)
                session.flush()
                session.refresh(merged)
                session.expunge(merged)
                rows.append(merged)
    return rows
