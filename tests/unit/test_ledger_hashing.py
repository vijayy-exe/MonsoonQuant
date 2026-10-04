from datetime import UTC, date, datetime

from mq.ledger.hashing import GENESIS_HASH, canonical_json, payload_hash, row_hash


def test_canonical_json_is_deterministic_regardless_of_key_order() -> None:
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_canonical_json_serialises_dates_and_datetimes() -> None:
    payload = {
        "as_of_date": date(2026, 10, 4),
        "issued_at": datetime(2026, 10, 4, 7, 0, tzinfo=UTC),
    }
    text = canonical_json(payload)
    assert "2026-10-04" in text


def test_payload_hash_changes_when_content_changes() -> None:
    h1 = payload_hash({"x": 1})
    h2 = payload_hash({"x": 2})
    assert h1 != h2
    assert len(h1) == 64


def test_row_hash_depends_on_both_prev_hash_and_payload() -> None:
    h_a = row_hash(GENESIS_HASH, "payload1")
    h_b = row_hash("some-other-prev", "payload1")
    assert h_a != h_b


def test_genesis_hash_is_64_zero_chars() -> None:
    assert GENESIS_HASH == "0" * 64
