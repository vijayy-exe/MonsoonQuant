from datetime import date
from pathlib import Path

import yaml

from mq.db.models import RawFile, Source
from mq.db.session import session_scope
from mq.specs.sources import SourceMetadata, list_registered_sources, register_source


def test_register_source_writes_yaml_and_db_rows(tmp_path: Path) -> None:
    doc = tmp_path / "ncdex_spec.pdf"
    doc.write_bytes(b"pretend contract spec bytes")

    sources_dir = tmp_path / "sources"
    raw_dir = sources_dir / "raw"
    metadata = SourceMetadata(
        source_id="test_ncdex_spec_rainchnnai",
        title="Test contract spec",
        publisher="NCDEX",
        url="https://example.invalid/spec.pdf",
        published_at=date(2026, 8, 31),
        effective_at=date(2026, 9, 1),
        licence="public",
    )

    yaml_path = register_source(doc, metadata, sources_dir=sources_dir, raw_dir=raw_dir)

    assert yaml_path.exists()
    payload = yaml.safe_load(yaml_path.read_text())
    assert payload["source_id"] == "test_ncdex_spec_rainchnnai"
    assert payload["publisher"] == "NCDEX"

    records = list_registered_sources(sources_dir=sources_dir)
    assert any(r["source_id"] == "test_ncdex_spec_rainchnnai" for r in records)

    digest = payload["sha256"]
    with session_scope() as session:
        source_row = session.get(Source, "test_ncdex_spec_rainchnnai")
        assert source_row is not None
        assert source_row.sha256 == digest

        raw_row = session.get(RawFile, digest)
        assert raw_row is not None
        assert raw_row.bytes == doc.stat().st_size

        # cleanup — these are test rows, not real registered sources
        session.delete(source_row)
        session.delete(raw_row)
