"""`mq ledger ...` — prediction ledger inspection (SPEC §2.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import typer

from mq.ledger.export import export_day
from mq.ledger.verify import verify_chain

app = typer.Typer(help="Inspect and verify the prediction ledger.", no_args_is_help=True)


@app.command("verify")
def verify() -> None:
    """Recompute the hash chain over every prediction_ledger row and fail
    loudly on any break."""
    report = verify_chain()
    if report.valid:
        typer.echo(f"OK — {report.n_rows} rows, chain intact.")
        return
    typer.echo(f"FAILED — {report.n_rows} rows, {len(report.breaks)} break(s):", err=True)
    for b in report.breaks:
        typer.echo(f"  row {b.row_id}: {b.reason}", err=True)
    raise typer.Exit(code=1)


@app.command("export")
def export(
    day: str | None = typer.Option(None, help="YYYY-MM-DD; defaults to today (UTC)."),
) -> None:
    """Export the given day's ledger rows to ledger/YYYY/MM/DD.jsonl."""
    target_day = date.fromisoformat(day) if day else datetime.now(UTC).date()
    out_path = export_day(target_day)
    if out_path is None:
        typer.echo(f"No ledger rows issued on {target_day}.")
        return
    typer.echo(f"Exported -> {out_path}")
