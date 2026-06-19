"""Binding-plan schema loading + validation (WMBT D001).

Defines and validates the binder's one project file — ``.atdd/binding.lock.yaml``
(the resolved binding plan: the substrate-lock digest the plan is keyed to, plus
per-convention entries recording which ``realizes_convention`` is bound-owned by
which implementation/workspace versus left to a legacy-fallback validator) —
against its canonical JSON schema. The schema ships as planner package data and is
resolved PACKAGE-RELATIVELY from the installed ``atdd`` package, so a pip-installed
core validates a binding plan without a repo checkout.

GREEN target: load ``binding-lock.schema.json`` and validate against it, mirroring
``atdd.substrate.schemas``.
"""
from __future__ import annotations

from pathlib import Path

BINDING_LOCK_SCHEMA = "binding-lock.schema.json"


class BindingSchemaError(ValueError):
    """A binding plan failed validation against its canonical schema."""


def _schema_dir() -> Path:  # pragma: no cover - trivial path helper (GREEN)
    import atdd

    return Path(atdd.__file__).resolve().parent / "planner" / "schemas"


def load_binding_lock_schema() -> dict:
    """Load the binding-lock JSON schema, resolved package-relatively. (GREEN)"""
    raise NotImplementedError("D001: load binding-lock.schema.json (GREEN)")


def validate_binding_lock(data: dict, *, source: str | Path = "<binding.lock.yaml>") -> None:
    """Validate a binding plan against its canonical schema, raising on violation.

    GREEN target: jsonschema.validate(data, load_binding_lock_schema()); on
    ValidationError raise BindingSchemaError with the offending path + message.
    """
    raise NotImplementedError("D001: validate binding plan against binding-lock schema (GREEN)")
