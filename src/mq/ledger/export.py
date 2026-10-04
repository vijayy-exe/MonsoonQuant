"""Daily ledger export to `ledger/YYYY/MM/DD.jsonl` (SPEC §2.1).

A separate job (not implemented here) is meant to commit this file to a
public git repo — the commit timestamp becomes independent proof the
forecast predates the outcome. That step needs a GitHub remote, which this
project doesn't have configured yet (see docs/STATUS.md); this function
only produces the local file.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import select

from mq.db.models import PredictionLedgerRow
from mq.db.session import session_scope
from mq.ledger.hashing import canonical_json

LEDGER_EXPORT_DIR = Path("ledger")


def export_day(day: date, *, export_dir: Path = LEDGER_EXPORT_DIR) -> Path | None:
    """Write every prediction_ledger row issued on `day` (UTC calendar date
    of `issued_at`) to `<export_dir>/YYYY/MM/DD.jsonl`. Returns None (and
    writes nothing) if there are no rows for that day."""
    with session_scope() as session:
        all_rows = (
            session.execute(select(PredictionLedgerRow).order_by(PredictionLedgerRow.id.asc()))
            .scalars()
            .all()
        )
        # Filtered in Python on the UTC calendar date of issued_at — the
        # ledger is small enough daily that a DB-side date-cast isn't worth
        # the extra complexity.
        rows = [r for r in all_rows if r.issued_at.date() == day]
        if not rows:
            return None

        out_path = export_dir / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}.jsonl"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as f:
            for row in rows:
                payload = {
                    "id": row.id,
                    "issued_at": row.issued_at.isoformat(),
                    "as_of_date": row.as_of_date.isoformat(),
                    "contract_code": row.contract_code,
                    "model_id": row.model_id,
                    "model_version": row.model_version,
                    "data_version": row.data_version,
                    "target": row.target,
                    "quantiles": row.quantiles,
                    "fair_value": str(row.fair_value) if row.fair_value is not None else None,
                    "fair_value_lo90": (
                        str(row.fair_value_lo90) if row.fair_value_lo90 is not None else None
                    ),
                    "fair_value_hi90": (
                        str(row.fair_value_hi90) if row.fair_value_hi90 is not None else None
                    ),
                    "payload_sha256": row.payload_sha256,
                    "prev_hash": row.prev_hash,
                    "row_hash": row.row_hash,
                }
                f.write(canonical_json(payload) + "\n")
        return out_path
