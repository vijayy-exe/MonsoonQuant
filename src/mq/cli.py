"""MonsoonQuant CLI entry point. Subcommands are added milestone by milestone
(sources, ledger, run, version show, ...) — see docs/STATUS.md."""

from __future__ import annotations

import importlib.metadata

import typer

from mq.config import get_settings
from mq.ledger.cli import app as ledger_app
from mq.logging import configure_logging, get_logger
from mq.research.cli import app as research_app
from mq.specs.sources_cli import app as sources_app
from mq.specs.specs_cli import app as specs_app

app = typer.Typer(
    name="mq",
    help="MonsoonQuant — rainfall-derivatives research platform CLI.",
    no_args_is_help=True,
)
app.add_typer(sources_app, name="sources")
app.add_typer(specs_app, name="specs")
app.add_typer(ledger_app, name="ledger")
app.add_typer(research_app, name="research")


@app.callback()
def _main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)


@app.command()
def version() -> None:
    """Print the installed monsoonquant package version."""
    log = get_logger(__name__)
    pkg_version = importlib.metadata.version("monsoonquant")
    typer.echo(pkg_version)
    log.info("version_check", version=pkg_version)


if __name__ == "__main__":
    app()
