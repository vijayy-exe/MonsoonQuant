"""`mq ledger ...` — prediction ledger inspection and live writes
(SPEC §2.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import typer

from mq.api.common import BASIS_YEARS, load_climate_idx, load_combined_rain_grid, load_resolved_spec
from mq.db.session import session_scope
from mq.forecasting.live import build_live_forecasts
from mq.ledger.export import export_day
from mq.ledger.verify import verify_chain
from mq.ledger.writer import write_forecast

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


@app.command("write-live")
def write_live(
    contract: str = typer.Option(..., "--contract", help="Contract code, e.g. RAINCHNNAI."),
    as_of: str | None = typer.Option(None, "--as-of", help="YYYY-MM-DD; defaults to today."),
) -> None:
    """Write real live forecast rows for the 4 newer forecasting-ladder
    rungs (enso_clim_v1/analog_v1/lgbm_q_v1/lgbm_q_cqr_v1) -- SPEC §7's
    own stated gap, M7 (see `mq.forecasting.live`'s module docstring).
    `clim_v1` is untouched -- it has its own existing live-row history
    from M1, left as-is per "never modify ledger rows without asking."
    Idempotent: re-running for a day/model already in the ledger is a
    safe no-op, same guarantee every ledger write already carries."""
    effective_as_of = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    with session_scope() as session:
        spec = load_resolved_spec(session, contract, contract)
        rain_grid = load_combined_rain_grid(effective_as_of)
        climate_idx = load_climate_idx(effective_as_of)
        data_version = (
            f"imd-1991-2020-full-plus-2023_n{len(BASIS_YEARS)}_spec-{spec.spec_version.isoformat()}"
        )
        forecasts = build_live_forecasts(
            spec,
            rain_grid,
            climate_idx,
            historical_years=BASIS_YEARS,
            as_of=effective_as_of,
            data_version=data_version,
        )

    for forecast in forecasts:
        row = write_forecast(forecast)
        if row is None:
            typer.echo(f"{forecast.model_id} {forecast.model_version}: already in ledger, skipped.")
        else:
            typer.echo(
                f"{forecast.model_id} {forecast.model_version}: wrote row {row.id} "
                f"(hash {row.row_hash[:12]}...)."
            )
