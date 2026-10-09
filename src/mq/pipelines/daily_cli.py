"""`mq run ...` (SPEC §8.1, §0.5's `make ingest`)."""

from __future__ import annotations

from datetime import date

import typer

from mq.pipelines.daily import run_daily

app = typer.Typer(help="Run the real daily/backfill ingestion pipeline.", no_args_is_help=True)


@app.command("daily")
def daily(
    as_of: str | None = typer.Option(None, "--as-of", help="YYYY-MM-DD; defaults to today."),
) -> None:
    """SPEC §8.1's daily DAG: fetch real IMD/ONI/DMI data, recompute the
    real CDR index, and write live forecasts for the 4 newer forecasting
    rungs -- all idempotent, safe to re-run. Exits non-zero if any step
    failed outright (not merely skipped -- see `mq.pipelines.daily`'s
    module docstring for what's skipped and why)."""
    effective_as_of = date.fromisoformat(as_of) if as_of else None
    report = run_daily(effective_as_of)
    for step in report.steps:
        marker = {"ok": "OK", "skipped": "SKIP", "failed": "FAIL"}[step.status]
        suffix = f" -- {step.detail}" if step.detail else ""
        typer.echo(f"[{marker}] {step.name}{suffix}")
    if not report.ok:
        raise typer.Exit(code=1)
