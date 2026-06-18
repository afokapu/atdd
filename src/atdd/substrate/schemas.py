"""Substrate schema loading + validation (WMBT D001).

Defines and validates the three canonical substrate files against their JSON
schemas: `.atdd/substrate.yaml` (intent), `.atdd/substrate.lock.yaml` (resolved,
digested state), and the registry index. Schemas ship as planner package data and
are resolved PACKAGE-RELATIVELY from the installed ``atdd`` package
(``Path(atdd.__file__).parent``, per coach.source-layout) so a pip-installed core
validates substrate files without a repo checkout.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import jsonschema

import atdd

SUBSTRATE_SCHEMA = "substrate.schema.json"
SUBSTRATE_LOCK_SCHEMA = "substrate-lock.schema.json"
REGISTRY_INDEX_SCHEMA = "registry-index.schema.json"


class SubstrateSchemaError(ValueError):
    """A substrate file failed validation against its canonical schema."""


def _schema_dir() -> Path:
    return Path(atdd.__file__).resolve().parent / "planner" / "schemas"


@functools.lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    """Load a substrate JSON schema by filename, resolved package-relatively."""
    path = _schema_dir() / name
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(data: dict, schema_name: str, source: str | Path) -> None:
    try:
        jsonschema.validate(instance=data, schema=load_schema(schema_name))
    except jsonschema.ValidationError as exc:
        loc = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        raise SubstrateSchemaError(
            f"{source}: schema violation at {loc}: {exc.message}"
        ) from exc


def validate_substrate(data: dict, *, source: str | Path = "<substrate.yaml>") -> None:
    """Validate substrate intent (`.atdd/substrate.yaml`) against its schema."""
    _validate(data, SUBSTRATE_SCHEMA, source)


def validate_lock(data: dict, *, source: str | Path = "<substrate.lock.yaml>") -> None:
    """Validate substrate lock (`.atdd/substrate.lock.yaml`) against its schema."""
    _validate(data, SUBSTRATE_LOCK_SCHEMA, source)


def validate_registry_index(data: dict, *, source: str | Path = "<registry index>") -> None:
    """Validate a registry index document against its schema."""
    _validate(data, REGISTRY_INDEX_SCHEMA, source)
