# URN: test:author-atdd-substrate:substrate-spine:C006-UNIT-001-manifests-validated
# Acceptance: acc:author-atdd-substrate:C006-UNIT-001-manifests-validated
# WMBT: wmbt:author-atdd-substrate:C006
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C006-UNIT-001 — extension/workspace/implementation manifests accept canonical shapes; wrong kind/id/version refused."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_manifest import (
    validate_extension_manifest,
    validate_implementation_manifest,
    validate_workspace_manifest,
)

_EXT = {
    "schema_version": "1.0.0",
    "extension_id": "acme.extension.component-header-validator",
    "kind": "extension",
    "owns": {"implementations": ["validators/component-header/atdd.implementation.yaml"]},
    "depends_on": {"workspaces": [{"id": "atdd.workspace.python-pytest", "contract": "^1.0.0"}]},
}
_WS = {
    "schema_version": "1.0.0",
    "workspace_id": "atdd.workspace.python-pytest",
    "kind": "workspace",
    "contract_version": "1.0.0",
    "runtime": {"language": "python", "runner": "pytest", "command": "pytest"},
    "discovers": {"implementations": ["**/atdd.implementation.yaml"], "requires_contract": "^1.0.0"},
}
_IMPL = {
    "schema_version": "1.0.0",
    "implementation_id": "component-header",
    "kind": "implementation",
    "subtype": "validator",
    "targets_workspace": "atdd.workspace.python-pytest",
    "contract_version": "1.0.0",
    "entrypoint": "src/check_component_header.py",
    "report": "src/check_component_header.py",
    "emits_rule_ids": ["coder.source.component-header-required"],
}


def test_canonical_manifests_accepted():
    validate_extension_manifest(_EXT)
    validate_workspace_manifest(_WS)
    validate_implementation_manifest(_IMPL)  # no raise


def test_extension_with_bad_workspace_dep_refused():
    bad = {**_EXT, "depends_on": {"workspaces": [{"id": "acme.extension.x", "contract": "^1.0.0"}]}}
    with pytest.raises(AuthorInputError) as exc:
        validate_extension_manifest(bad)
    assert exc.value.field == "workspace"  # an extension-scope id is not a valid workspace target


def test_workspace_without_contract_version_refused():
    bad = {k: v for k, v in _WS.items() if k != "contract_version"}
    with pytest.raises(AuthorInputError) as exc:
        validate_workspace_manifest(bad)
    assert exc.value.field == "contract_version"


def test_implementation_wrong_kind_refused():
    bad = {**_IMPL, "kind": "workspace"}
    with pytest.raises(AuthorInputError) as exc:
        validate_implementation_manifest(bad)
    assert exc.value.field == "kind"
