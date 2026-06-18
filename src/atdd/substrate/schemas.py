"""Substrate schema loading + validation (WMBT D001).

Defines and validates the three canonical substrate files against their JSON
schemas: `.atdd/substrate.yaml` (intent), `.atdd/substrate.lock.yaml` (resolved,
digested state), and the registry index. Schemas ship as planner package data so
a pip-installed core resolves them package-relatively (no repo checkout).

RED: the validators are unimplemented stubs; D001's tests fail until GREEN ships
the schemas + validation.
"""
from __future__ import annotations

from pathlib import Path

# Schemas ship under the planner schemas package data (resolved package-relatively
# in GREEN via importlib / atdd.__file__, mirroring compose.installed_core_node_ids).
SUBSTRATE_SCHEMA = "substrate.schema.json"
SUBSTRATE_LOCK_SCHEMA = "substrate-lock.schema.json"
REGISTRY_INDEX_SCHEMA = "registry-index.schema.json"


class SubstrateSchemaError(ValueError):
    """A substrate file failed validation against its canonical schema."""


def load_schema(name: str) -> dict:
    """Load a substrate JSON schema by filename, package-relatively. (GREEN)"""
    raise NotImplementedError("D001: load_schema not implemented (RED)")


def validate_substrate(data: dict, *, source: str | Path = "<substrate.yaml>") -> None:
    """Validate substrate intent (`.atdd/substrate.yaml`) against its schema. (GREEN)"""
    raise NotImplementedError("D001: validate_substrate not implemented (RED)")


def validate_lock(data: dict, *, source: str | Path = "<substrate.lock.yaml>") -> None:
    """Validate substrate lock (`.atdd/substrate.lock.yaml`) against its schema. (GREEN)"""
    raise NotImplementedError("D001: validate_lock not implemented (RED)")


def validate_registry_index(data: dict, *, source: str | Path = "<registry index>") -> None:
    """Validate a registry index document against its schema. (GREEN)"""
    raise NotImplementedError("D001: validate_registry_index not implemented (RED)")
