"""Canonical JSON + the two-hash scheme behind the prediction ledger
(SPEC §2.1): `payload_sha256` hashes a row's content; `row_hash` folds in
`prev_hash` so the whole table forms one append-only chain."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

GENESIS_HASH = "0" * 64


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"not JSON-serialisable for canonical hashing: {type(value)!r}")


def canonical_json(data: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, fixed separators, ISO dates — the
    same dict always serialises to the same bytes, on any machine."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_json_default)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_hash(core_fields: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(core_fields))


def row_hash(prev_hash: str, payload_sha256: str) -> str:
    return sha256_hex(prev_hash + payload_sha256)
