# URN: test:admit-substrate:substrate-admission:D001-UNIT-001-substrate-schemas
# Acceptance: acc:admit-substrate:D001-UNIT-001-substrate-schemas
# WMBT: wmbt:admit-substrate:D001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""D001-UNIT-001 — a well-formed substrate.yaml, substrate.lock.yaml, and registry
index validate against their canonical schemas; malformed variants (missing
required field, bad version shape, unknown top-level key) are refused."""
from __future__ import annotations

import copy

import pytest

from atdd.substrate import schemas

GOOD_SUBSTRATE = {
    "schema_version": "1.0.0",
    "registries": [
        {
            "id": "atdd.official",
            "type": "git",
            "source": "https://github.com/afokapu/atdd-extensions",
            "path": "registry/index.yaml",
            "trust": "official",
        }
    ],
    "substrate": [{"ref": "component-header", "version": "^0.1.0"}],
}

GOOD_LOCK = {
    "schema_version": "1.0.0",
    "artifacts": [
        {
            "id": "acme.extension.component-header-validator",
            "kind": "extension",
            "version": "0.1.0",
            "source": "registry:atdd.official",
            "digest": "sha256:" + "a" * 64,
            "installed_path": ".atdd/extensions/acme.extension.component-header-validator/0.1.0",
            "enabled": True,
            "workspaces": [
                {"id": "atdd.workspace.python-pytest", "version": "1.0.0", "contract_version": "1.0.0"}
            ],
        }
    ],
}

GOOD_REGISTRY = {
    "schema_version": "1.0.0",
    "entries": [
        {
            "id": "acme.extension.component-header-validator",
            "kind": "extension",
            "aliases": ["component-header", "source-header"],
            "display_name": "Component Header Validator",
            "summary": "Validates component headers in source files.",
            "tags": ["source", "header", "python"],
            "latest_version": "0.1.0",
            "versions": ["0.1.0"],
        }
    ],
}


def test_well_formed_files_validate() -> None:
    schemas.validate_substrate(GOOD_SUBSTRATE)
    schemas.validate_lock(GOOD_LOCK)
    schemas.validate_registry_index(GOOD_REGISTRY)


def test_lock_entry_missing_digest_is_refused() -> None:
    bad = copy.deepcopy(GOOD_LOCK)
    del bad["artifacts"][0]["digest"]
    with pytest.raises(schemas.SubstrateSchemaError):
        schemas.validate_lock(bad)


def test_intent_entry_missing_ref_is_refused() -> None:
    bad = copy.deepcopy(GOOD_SUBSTRATE)
    del bad["substrate"][0]["ref"]
    with pytest.raises(schemas.SubstrateSchemaError):
        schemas.validate_substrate(bad)


def test_registry_non_semver_version_is_refused() -> None:
    bad = copy.deepcopy(GOOD_REGISTRY)
    bad["entries"][0]["latest_version"] = "not-a-version"
    with pytest.raises(schemas.SubstrateSchemaError):
        schemas.validate_registry_index(bad)


def test_substrate_unknown_top_level_key_is_refused() -> None:
    bad = copy.deepcopy(GOOD_SUBSTRATE)
    bad["nonsense"] = True
    with pytest.raises(schemas.SubstrateSchemaError):
        schemas.validate_substrate(bad)
