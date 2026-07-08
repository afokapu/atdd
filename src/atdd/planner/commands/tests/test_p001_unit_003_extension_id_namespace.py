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


# --------------------------------------------------------------------------- #
# Prepared-migration boundary (audit #1345 → gated on #1343 + #1344)
#
# These assert the *target* persona-aware extension grammar
# (``<publisher>.extension.<persona>.<artifact-name>``, persona ∈
# {planner,tester,coder,coach}) that #1343 will introduce and #1344 will adopt
# for the installed official extensions. They must FAIL against today's
# single three-segment ``_PKG_ID_RE`` (author_context.py:26), so they are
# ``xfail(strict=True)``: when #1343 splits the grammar they flip to XPASS,
# which fails the strict xfail and prompts removing the marker. See
# docs/1345-extension-id-grammar-audit.md.
#
# The workspace invariant below is NOT gated — workspace IDs stay three-segment
# — so it is a plain passing test that must survive the #1343 flip.
# --------------------------------------------------------------------------- #
_GATED = "grammar split gated on #1343; installed-extension rename gated on #1344"


@pytest.mark.xfail(reason=_GATED, strict=True)
def test_four_segment_persona_extension_id_accepted():
    # Official persona-aware IDs (#1344 target). allow_reserved: structural
    # validation of an official ``atdd.*`` manifest.
    validate_extension_id("atdd.extension.coder.base", allow_reserved=True)
    validate_extension_id("atdd.extension.tester.base", allow_reserved=True)
    # Third-party persona-aware ID (#1343 grammar, non-reserved publisher).
    validate_extension_id("productos.extension.coach.lifecycle")


@pytest.mark.xfail(reason=_GATED, strict=True)
def test_three_segment_extension_id_rejected():
    # Once #1343 makes the extension grammar persona-aware, the legacy
    # three-segment form must be refused (no compatibility alias — #1345
    # non-goal). Today it is (wrongly, per the target) accepted.
    with pytest.raises(AuthorInputError):
        validate_extension_id("acme.extension.demo")


@pytest.mark.xfail(reason=_GATED, strict=True)
def test_extension_persona_validated_against_core_vocabulary():
    # A well-formed four-segment ID whose persona segment is not one of the
    # four core personas must be refused; a valid-persona ID must pass. Today
    # both are refused as malformed (four segments), so the pair fails.
    validate_extension_id("productos.extension.tester.jira-sync")
    with pytest.raises(AuthorInputError):
        validate_extension_id("productos.extension.notapersona.jira-sync")


def test_workspace_id_stays_three_segment_boundary():
    # Invariant (NOT gated): workspace grammar remains three-segment across the
    # #1343 extension flip — a three-segment workspace ID validates and a
    # four-segment one is refused.
    validate_workspace_id("acme.workspace.python-pytest")  # no raise
    with pytest.raises(AuthorInputError):
        validate_workspace_id("acme.workspace.coder.python-pytest")
