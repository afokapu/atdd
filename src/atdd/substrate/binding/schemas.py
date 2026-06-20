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

import functools
import json
from pathlib import Path

import jsonschema

BINDING_LOCK_SCHEMA = "binding-lock.schema.json"


class BindingSchemaError(ValueError):
    """A binding plan failed validation against its canonical schema."""


def _schema_dir() -> Path:
    import atdd

    return Path(atdd.__file__).resolve().parent / "planner" / "schemas"


@functools.lru_cache(maxsize=None)
def load_binding_lock_schema() -> dict:
    """Load the binding-lock JSON schema, resolved package-relatively from the
    installed ``atdd`` package (so a pip-installed core validates with no checkout)."""
    return json.loads((_schema_dir() / BINDING_LOCK_SCHEMA).read_text(encoding="utf-8"))


def validate_binding_lock(data: dict, *, source: str | Path = "<binding.lock.yaml>") -> None:
    """Validate a binding plan against its canonical schema, raising on violation."""
    try:
        jsonschema.validate(instance=data, schema=load_binding_lock_schema())
    except jsonschema.ValidationError as exc:
        loc = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        raise BindingSchemaError(
            f"{source}: schema violation at {loc}: {exc.message}"
        ) from exc
