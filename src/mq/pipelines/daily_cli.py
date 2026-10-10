"""`mq run ...` (SPEC §8.1, §0.5's `make ingest`)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import typer

from mq.pipelines.daily import run_daily
from mq.pipelines.dq import DQGateFailedError
from mq.pipelines.ncdex import write_market_quotes

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


@app.command("bhavcopy")
def bhavcopy(
    csv_path: Path = typer.Argument(..., exists=True, readable=True, dir_okay=False),
    as_of: str | None = typer.Option(
        None, "--as-of", help="Trading date this bhavcopy covers; defaults to today."
    ),
) -> None:
    """Ingest one real NCDEX UDiFF bhavcopy CSV, downloaded manually from
    ncdex.com/markets/bhavcopy -- the site's own `/api/bhavcopy` backend
    sits behind a fingerprint bot-detection challenge, not worked around
    (docs/DECISIONS.md, 2026-10-04). Hashes the file immutably, parses
    the real documented UDiFF schema, filters to RAINCHNNAI/RAINMUMBAI,
    runs the DQ gate, and upserts into `market_quotes`. Safe to re-run
    the same file (idempotent upsert on (series_id, trade_date))."""
    effective_as_of = date.fromisoformat(as_of) if as_of else date.today()
    try:
        n = write_market_quotes(csv_path, as_of=effective_as_of)
    except DQGateFailedError as exc:
        typer.echo(f"DQ gate failed, nothing written: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if n == 0:
        typer.echo("0 rows written -- no RAINCHNNAI/RAINMUMBAI rows found in this file.")
    else:
        typer.echo(f"Wrote {n} market_quotes row(s) from {csv_path}.")
