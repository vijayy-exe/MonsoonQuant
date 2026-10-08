"""`mq specs ...` — validating ContractSpec YAMLs (SPEC §7.1) and
(re-)registering the real contracts into the DB."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import typer

from mq.specs.loader import DraftSpecRejectedError, find_pending_fields, load_contract_spec
from mq.specs.registry import register_contract_spec, register_listed_series

app = typer.Typer(help="Validate contract-spec YAMLs.", no_args_is_help=True)

# The project's own real, known contracts -- there are exactly two, with
# a fixed, documented set of real listed series each (not a flexible
# generic interface, since this isn't a generic fact: it's this
# project's actual NCDEX contract calendar). See docs/VERIFY.md/V1-V11
# for how these were resolved, and docs/methods/api.md for the real
# finding this command exists to fix: the registry.register_* calls are
# idempotent upserts, but nothing had ever made them part of a
# repeatable setup step -- so a `contracts`/`contract_specs` row that a
# test's own cleanup deletes (tests/integration/test_registry_write.py
# legitimately DELETEs rows under contract_code='RAINCHNNAI' as its own
# teardown, since it exercises these same functions against the real
# spec file) stayed gone until someone noticed the API returning 404s
# for a real series and manually re-ran the registration ad hoc --
# caught 3 times across sessions before this command existed.
_REAL_CONTRACTS: list[tuple[Path, list[tuple[int, int]]]] = [
    (Path("specs/contracts/RAINCHNNAI/2026-08-31.yaml"), [(2026, 10), (2026, 11), (2026, 12)]),
    (
        Path("specs/contracts/RAINMUMBAI/2026-05-29.yaml"),
        [(2026, 6), (2026, 7), (2026, 8), (2026, 9)],
    ),
]


@app.command("seed-registry")
def seed_registry() -> None:
    """(Re-)register both real contract specs and their real listed
    series into the DB -- idempotent (session.merge upserts), safe to
    run any number of times, including right after a test (or anything
    else) has deleted the rows. `as_of` is today, so each series' own
    active/expired status is always recomputed correctly for whenever
    this is actually run, not frozen to a stale reference date."""
    today = date.today()
    for path, expiry_months in _REAL_CONTRACTS:
        spec = load_contract_spec(path)
        register_contract_spec(spec)
        rows = register_listed_series(spec, expiry_months=expiry_months, as_of=today)
        series_ids = ", ".join(r.series_id for r in rows)
        typer.echo(f"{spec.contract_code} ({spec.spec_version}): {series_ids}")


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
