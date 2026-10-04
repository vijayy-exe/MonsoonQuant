"""`mq sources ...` — the source document register (SPEC F01)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import typer

from mq.logging import get_logger
from mq.specs.sources import SourceMetadata, list_registered_sources, register_source

app = typer.Typer(help="Register and inspect external source documents.", no_args_is_help=True)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@app.command("add")
def add(
    file_path: Path = typer.Argument(..., exists=True, readable=True, dir_okay=False),
    source_id: str = typer.Option(..., help="Stable id, e.g. ncdex_spec_rainchnnai_2026"),
    title: str | None = typer.Option(None),
    publisher: str | None = typer.Option(None),
    url: str | None = typer.Option(None),
    published_at: str | None = typer.Option(None, help="YYYY-MM-DD"),
    effective_at: str | None = typer.Option(None, help="YYYY-MM-DD"),
    licence: str | None = typer.Option(None),
) -> None:
    """Hash, immutably store, and register a source document (PDF/CSV/etc.)."""
    log = get_logger(__name__)
    metadata = SourceMetadata(
        source_id=source_id,
        title=title,
        publisher=publisher,
        url=url,
        published_at=_parse_date(published_at),
        effective_at=_parse_date(effective_at),
        licence=licence,
    )
    yaml_path = register_source(file_path, metadata)
    log.info("source_registered", source_id=source_id, yaml_path=str(yaml_path))
    typer.echo(f"Registered {source_id} -> {yaml_path}")


@app.command("list")
def list_sources() -> None:
    """List every registered source document."""
    records = list_registered_sources()
    if not records:
        typer.echo("No sources registered yet. Use `mq sources add`.")
        return
    for record in records:
        typer.echo(
            f"{record['source_id']:<40} sha256={record['sha256'][:12]}  "
            f"effective_at={record.get('effective_at')}  url={record.get('url')}"
        )
