"""Loads and validates ContractSpec YAMLs (SPEC §7.1).

A spec with any field still equal to the "TODO_VERIFY" sentinel is a DRAFT:
usable for scaffolding and tests, but the loader refuses it for anything
real unless the caller explicitly passes `allow_draft=True`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mq.specs.contract import TODO_VERIFY, ContractSpec


class DraftSpecRejectedError(RuntimeError):
    """Raised when a spec still has unresolved VERIFY fields and the caller
    did not pass allow_draft=True."""

    def __init__(self, pending_fields: list[str]):
        self.pending_fields = pending_fields
        joined = ", ".join(pending_fields)
        super().__init__(
            f"spec has unresolved VERIFY fields: {joined}. "
            "Pass allow_draft=True (or --allow-draft) if this is intentional."
        )


def find_pending_fields(data: Any, *, path: str = "") -> list[str]:
    """Recursively find every dotted field path whose value is the
    TODO_VERIFY sentinel, in a parsed (dict/list/scalar) spec structure."""
    pending: list[str] = []
    if data == TODO_VERIFY:
        pending.append(path or "<root>")
    elif isinstance(data, dict):
        for key, value in data.items():
            child_path = f"{path}.{key}" if path else str(key)
            pending.extend(find_pending_fields(value, path=child_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            pending.extend(find_pending_fields(item, path=f"{path}[{i}]"))
    return pending


def is_draft(spec: ContractSpec) -> bool:
    return len(find_pending_fields(spec.model_dump(mode="json"))) > 0


def load_contract_spec(path: Path, *, allow_draft: bool = False) -> ContractSpec:
    """Parse and validate a ContractSpec YAML. Raises DraftSpecRejectedError
    if any VERIFY-dependent field is still TODO_VERIFY and allow_draft is
    False."""
    raw = yaml.safe_load(path.read_text())
    spec = ContractSpec.model_validate(raw)
    pending = find_pending_fields(spec.model_dump(mode="json"))
    if pending and not allow_draft:
        raise DraftSpecRejectedError(pending)
    return spec
