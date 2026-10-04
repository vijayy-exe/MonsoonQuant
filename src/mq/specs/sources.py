"""Source document register (SPEC F01, §6.1 `sources` + `raw_files`).

Every external document (contract-spec PDF, data-provider terms, etc.) is
hashed, stored immutably under specs/sources/raw/, and recorded both as a
YAML sidecar (human-reviewable, git-tracked) and a DB row (queryable
lineage). Raw files are never overwritten — re-registering identical
content is a no-op on the object store.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from mq.db.models import RawFile, Source
from mq.db.session import session_scope

SOURCES_DIR = Path("specs/sources")
RAW_DIR = SOURCES_DIR / "raw"


class SourceMetadata(BaseModel):
    source_id: str
    title: str | None = None
    publisher: str | None = None
    url: str | None = None
    published_at: date | None = None
    effective_at: date | None = None
    licence: str | None = None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def store_raw_file(file_path: Path, *, raw_dir: Path = RAW_DIR) -> tuple[str, Path]:
    """Content-address `file_path` into `raw_dir`. Pure filesystem operation,
    no DB — returns (sha256, stored_path). Never overwrites an existing
    object; identical content under the same hash is left as-is."""
    digest = sha256_of(file_path)
    raw_dir.mkdir(parents=True, exist_ok=True)
    object_path = raw_dir / f"{digest}{file_path.suffix}"
    if not object_path.exists():
        shutil.copy2(file_path, object_path)
    return digest, object_path


def register_source(
    file_path: Path,
    metadata: SourceMetadata,
    *,
    sources_dir: Path = SOURCES_DIR,
    raw_dir: Path = RAW_DIR,
) -> Path:
    """Hash, immutably store, and record `file_path` as a registered source:
    writes a YAML sidecar under `sources_dir` and upserts the `sources` /
    `raw_files` DB rows. Returns the path to the written YAML sidecar."""
    digest, object_path = store_raw_file(file_path, raw_dir=raw_dir)
    downloaded_at = datetime.now(UTC)
    object_key = str(object_path)

    sources_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = sources_dir / f"{metadata.source_id}.yaml"
    yaml_payload = {
        "source_id": metadata.source_id,
        "title": metadata.title,
        "publisher": metadata.publisher,
        "url": metadata.url,
        "published_at": metadata.published_at.isoformat() if metadata.published_at else None,
        "effective_at": metadata.effective_at.isoformat() if metadata.effective_at else None,
        "downloaded_at": downloaded_at.isoformat(),
        "sha256": digest,
        "object_key": object_key,
        "licence": metadata.licence,
    }
    yaml_path.write_text(yaml.safe_dump(yaml_payload, sort_keys=False))

    with session_scope() as session:
        session.merge(
            RawFile(
                sha256=digest,
                source_name=metadata.source_id,
                url=metadata.url,
                fetched_at=downloaded_at,
                bytes=file_path.stat().st_size,
                object_key=object_key,
            )
        )
        session.merge(
            Source(
                source_id=metadata.source_id,
                title=metadata.title,
                publisher=metadata.publisher,
                url=metadata.url,
                published_at=metadata.published_at,
                effective_at=metadata.effective_at,
                downloaded_at=downloaded_at,
                sha256=digest,
                object_key=object_key,
                licence=metadata.licence,
            )
        )

    return yaml_path


def list_registered_sources(*, sources_dir: Path = SOURCES_DIR) -> list[dict[str, Any]]:
    """Read back every registered source's YAML sidecar (no DB hit)."""
    if not sources_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for yaml_path in sorted(sources_dir.glob("*.yaml")):
        records.append(yaml.safe_load(yaml_path.read_text()))
    return records
