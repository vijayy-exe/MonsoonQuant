"""FastAPI dependencies — a thin wrapper around `mq.db.session`'s
existing session-scope pattern so routes get the same commit/rollback
semantics every other DB-writing module in this project already uses."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from mq.db.session import get_session_factory


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
