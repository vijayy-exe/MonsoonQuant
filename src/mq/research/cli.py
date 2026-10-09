"""`mq research ...` (SPEC §17 Principle 10, §18)."""

from __future__ import annotations

from pathlib import Path

import typer

from mq.research.reproduce import reproduce_all

app = typer.Typer(help="Regenerate the paper's real, measured figures.", no_args_is_help=True)


@app.command("reproduce")
def reproduce(
    output_dir: str = typer.Option(
        "research/figures", "--output-dir", help="Where to write the regenerated figure JSON files."
    ),
) -> None:
    """Regenerate the preprint's real figures (M4 burn/distribution, M7
    forecasting backtest, M9 hedge, M10 basis grid, M11 parametric)
    from real local data (SPEC §17: "Clean checkout -> make reproduce
    -> same figures"). Needs the real IMD/ONI/DMI backfill already run
    -- see docs/STATUS.md's "How to resume work" -- `data/` is
    deliberately never committed to git."""
    typer.echo("Regenerating real figures from local data (this reads the full IMD backfill)...")
    paths = reproduce_all(Path(output_dir))
    for name, path in paths.items():
        typer.echo(f"  {name} -> {path}")
    typer.echo("Done.")
