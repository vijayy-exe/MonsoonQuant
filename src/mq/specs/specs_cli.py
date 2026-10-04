"""`mq specs ...` — validating ContractSpec YAMLs (SPEC §7.1)."""

from __future__ import annotations

from pathlib import Path

import typer

from mq.specs.loader import DraftSpecRejectedError, find_pending_fields, load_contract_spec

app = typer.Typer(help="Validate contract-spec YAMLs.", no_args_is_help=True)


@app.command("validate")
def validate(
    path: Path = typer.Argument(..., exists=True, readable=True, dir_okay=False),
    allow_draft: bool = typer.Option(False, "--allow-draft", help="Permit TODO_VERIFY fields."),
) -> None:
    """Validate a ContractSpec YAML, rejecting unresolved VERIFY fields
    unless --allow-draft is passed."""
    try:
        spec = load_contract_spec(path, allow_draft=allow_draft)
    except DraftSpecRejectedError as exc:
        typer.echo(f"REJECTED (draft, use --allow-draft): {exc}", err=True)
        raise typer.Exit(code=1) from exc

    pending = find_pending_fields(spec.model_dump(mode="json"))
    if pending:
        typer.echo(f"DRAFT — {spec.contract_code} ({spec.spec_version}): OK with --allow-draft")
        typer.echo(f"  {len(pending)} field(s) still pending VERIFY: {', '.join(pending)}")
    else:
        typer.echo(f"VALID — {spec.contract_code} ({spec.spec_version}): no pending VERIFY fields")
