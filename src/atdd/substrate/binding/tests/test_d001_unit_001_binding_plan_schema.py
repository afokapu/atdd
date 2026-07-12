# URN: test:bind-substrate-runtime:substrate-binding:D001-UNIT-001-binding-plan-schema
# Acceptance: acc:bind-substrate-runtime:D001-UNIT-001-binding-plan-schema
# WMBT: wmbt:bind-substrate-runtime:D001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""D001-UNIT-001 — a well-formed binding plan validates against its schema;
malformed variants (missing the keyed digest, a bound entry missing
implementation_id, an unknown disposition, a non-SemVer contract_version) are
refused."""
from __future__ import annotations

import copy

import pytest

from atdd.substrate.binding import schemas

GOOD_BINDING_PLAN = {
    "schema_version": "1.0.0",
    "substrate_lock_digest": "sha256:" + "a" * 64,
    "conventions": [
        {
            "convention_id": "github.pr.merge-blocks-on-pre-smoke-close",
            "disposition": "bound",
            "implementation_id": "github.pr.merge-blocks-on-pre-smoke-close.impl",
            "workspace_id": "atdd.workspace.python-pytest",
            "contract_version": "1.0.0",
        },
        {
            "convention_id": "coach.pr.runtime-artifacts-blocked",
            "disposition": "legacy-fallback",
        },
    ],
}


def test_well_formed_plan_validates() -> None:
    schemas.validate_binding_lock(GOOD_BINDING_PLAN)


def test_missing_substrate_lock_digest_is_refused() -> None:
    bad = copy.deepcopy(GOOD_BINDING_PLAN)
    del bad["substrate_lock_digest"]
    with pytest.raises(schemas.BindingSchemaError):
        schemas.validate_binding_lock(bad)


def test_bound_entry_missing_implementation_id_is_refused() -> None:
    bad = copy.deepcopy(GOOD_BINDING_PLAN)
    del bad["conventions"][0]["implementation_id"]
    with pytest.raises(schemas.BindingSchemaError):
        schemas.validate_binding_lock(bad)


def test_unknown_disposition_is_refused() -> None:
    bad = copy.deepcopy(GOOD_BINDING_PLAN)
    bad["conventions"][0]["disposition"] = "shadow-maybe"
    with pytest.raises(schemas.BindingSchemaError):
        schemas.validate_binding_lock(bad)


def test_non_semver_contract_version_is_refused() -> None:
    bad = copy.deepcopy(GOOD_BINDING_PLAN)
    bad["conventions"][0]["contract_version"] = "not-a-version"
    with pytest.raises(schemas.BindingSchemaError):
        schemas.validate_binding_lock(bad)
