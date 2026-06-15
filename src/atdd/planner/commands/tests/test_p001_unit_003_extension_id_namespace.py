# URN: test:author-atdd-substrate:substrate-spine:P001-UNIT-003-extension-id-namespace
# Acceptance: acc:author-atdd-substrate:P001-UNIT-003-extension-id-namespace
# WMBT: wmbt:author-atdd-substrate:P001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""P001-UNIT-003 — package ids follow <publisher>.<scope>.<name>; scope ∈ {core,
extension, workspace}; wrong scope + reserved atdd publisher refused."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_context import (
    resolve_context,
    validate_extension_id,
    validate_workspace_id,
)


def test_well_formed_id_accepted():
    validate_extension_id("bromohub.extension.component-header-validator")  # no raise
    assert resolve_context(extension="bromohub.extension.python-pytest").extension_id == "bromohub.extension.python-pytest"


def test_malformed_id_refused():
    with pytest.raises(AuthorInputError) as exc:
        resolve_context(extension="bromohub.demo")  # two segments
    assert exc.value.field == "extension"


def test_core_scope_refused_under_extension():
    with pytest.raises(AuthorInputError) as exc:
        resolve_context(extension="bromohub.core.something")
    assert exc.value.field == "extension"
    assert "core" in str(exc.value).lower()


def test_reserved_atdd_publisher_refused():
    with pytest.raises(AuthorInputError) as exc:
        resolve_context(extension="atdd.extension.python-pytest")
    assert exc.value.field == "extension"
    assert "atdd" in str(exc.value).lower() and "reserved" in str(exc.value).lower()


def test_workspace_id_accepted():
    validate_workspace_id("acme.workspace.python-pytest")  # no raise


def test_workspace_validator_refuses_extension_scope():
    # the `workspace` validator rejects a `extension`-scoped id (cross-scope guard)
    with pytest.raises(AuthorInputError) as exc:
        validate_workspace_id("acme.extension.python-pytest")
    assert exc.value.field == "workspace"
    assert "workspace" in str(exc.value).lower()


def test_extension_validator_refuses_workspace_scope():
    # symmetric: the `extension` validator rejects a `workspace`-scoped id
    with pytest.raises(AuthorInputError) as exc:
        validate_extension_id("acme.workspace.python-pytest")
    assert exc.value.field == "extension"


def test_reserved_atdd_publisher_refused_for_workspace():
    with pytest.raises(AuthorInputError) as exc:
        validate_workspace_id("atdd.workspace.python-pytest")
    assert exc.value.field == "workspace"
    assert "reserved" in str(exc.value).lower()
