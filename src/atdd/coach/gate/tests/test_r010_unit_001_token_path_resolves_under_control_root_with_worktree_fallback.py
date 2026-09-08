# URN: test:govern-lifecycle:operator-approval-token-gate:R010-UNIT-001-token-path-resolves-under-control-root-with-worktree-fallback
# Acceptance: acc:govern-lifecycle:R010-UNIT-001-token-path-resolves-under-control-root-with-worktree-fallback
# WMBT: wmbt:govern-lifecycle:R010
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""R010-UNIT-001 — the token path is Control-Root-anchored, with a worktree fallback.

The resolver is handed a CHILD worktree nested under a Control Root and must
answer with the PARENT Control Root's ``.atdd/runtime/`` path — the base every
other operational reader has resolved through since #1346 — never the child's.
When only a legacy worktree-local token exists it is still located, so a token
dropped before #1376 does not force the operator to re-approve.

Hermetic: a real marker-based Control Root layout under ``tmp_path`` (an
initialized ``.atdd/state/`` at the parent, a bare child directory below it), so
``resolve_operational_root``'s real rules decide — no monkeypatched resolver, no
git, no live Control Root touched. The layout precondition is asserted first, so
a resolution that ever collapsed parent and child would FAIL this test rather
than let its later assertions pass vacuously.

RED state: ``atdd.coach.gate.approval_paths`` does not exist — the token path is
computed inline in ``ApprovalTokenGateCheck.run`` as ``ctx.worktree / rel``, with
no seam to resolve and no fallback to exercise.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.gate.approval import approval_relpath
from atdd.coach.gate.approval_paths import (
    approval_control_root,
    approval_token_path,
    locate_approval_token,
)

pytestmark = [pytest.mark.platform]

_ISSUE, _FROM, _TO = 999999, "PLANNED", "RED"


@pytest.fixture
def nested_worktree(tmp_path: Path):
    """A child worktree nested under an initialized Control Root.

    ``.atdd/state/`` is a CONTROL_ROOT_MARKER_DIR, so the parent is a real
    Control Root; the child carries nothing, so resolution walks up to it.
    """
    control_root = tmp_path / "project"
    (control_root / ".atdd" / "state").mkdir(parents=True)
    child = control_root / "feat-some-worktree"
    child.mkdir()
    return control_root, child


def test_layout_precondition_control_root_is_the_parent_not_the_child(nested_worktree):
    """Guard: the fixture really does resolve child -> parent.

    Without this, every assertion below would also pass if the resolver simply
    echoed the child back — the exact defect under test.
    """
    control_root, child = nested_worktree
    assert approval_control_root(child) == control_root.resolve()
    assert approval_control_root(child) != child.resolve()


def test_canonical_token_path_is_anchored_at_the_control_root(nested_worktree):
    """R010-UNIT-001: the base moves to the Control Root; the relpath does not."""
    control_root, child = nested_worktree
    rel = approval_relpath(_ISSUE, _FROM, _TO)

    resolved = approval_token_path(child, _ISSUE, _FROM, _TO)

    assert resolved == control_root.resolve() / rel
    assert resolved != child / rel  # the pre-#1376 answer


def test_relpath_shape_is_unchanged(nested_worktree):
    """Only the base moves — approval_relpath's shape stays byte-identical."""
    assert approval_relpath(_ISSUE, _FROM, _TO) == Path(
        f".atdd/runtime/issue-{_ISSUE}/approvals/{_FROM}-{_TO}.json"
    )


def test_control_root_token_is_the_one_located(nested_worktree):
    """Arrangement (a): a token under the shared Control Root is found."""
    control_root, child = nested_worktree
    token = control_root / approval_relpath(_ISSUE, _FROM, _TO)
    token.parent.mkdir(parents=True)
    token.write_text(json.dumps({"issue": _ISSUE}))

    location = locate_approval_token(child, _ISSUE, _FROM, _TO)

    assert location.exists is True
    assert location.legacy is False
    assert location.path == token.resolve()


def test_legacy_worktree_local_token_still_resolves(nested_worktree):
    """Arrangement (b): back-compat — a pre-#1376 worktree-local token still resolves."""
    control_root, child = nested_worktree
    legacy = child / approval_relpath(_ISSUE, _FROM, _TO)
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"issue": _ISSUE}))
    assert not (control_root / approval_relpath(_ISSUE, _FROM, _TO)).exists()

    location = locate_approval_token(child, _ISSUE, _FROM, _TO)

    assert location.exists is True
    assert location.legacy is True
    assert location.path == legacy


def test_control_root_token_wins_over_a_worktree_local_one(nested_worktree):
    """With both present the shared Control Root is authoritative, not the worktree."""
    control_root, child = nested_worktree
    rel = approval_relpath(_ISSUE, _FROM, _TO)
    for base in (control_root, child):
        (base / rel).parent.mkdir(parents=True)
        (base / rel).write_text(json.dumps({"issue": _ISSUE, "base": str(base)}))

    location = locate_approval_token(child, _ISSUE, _FROM, _TO)

    assert location.legacy is False
    assert location.path == (control_root / rel).resolve()


def test_absent_token_reports_the_canonical_control_root_path(nested_worktree):
    """No token anywhere: exists is False and the path named is the canonical one."""
    control_root, child = nested_worktree

    location = locate_approval_token(child, _ISSUE, _FROM, _TO)

    assert location.exists is False
    assert location.legacy is False
    assert location.path == control_root.resolve() / approval_relpath(_ISSUE, _FROM, _TO)


def test_unresolvable_control_root_degrades_to_the_worktree(tmp_path: Path):
    """A bare directory with no Control Root above it answers with itself.

    This is what keeps single-repo layouts, consumer repos, and every hermetic
    test that hands a bare tmp dir as the worktree behaving exactly as before.
    """
    bare = tmp_path / "no-control-root"
    bare.mkdir()

    assert approval_control_root(bare) == bare.resolve()
    assert approval_token_path(bare, _ISSUE, _FROM, _TO) == bare.resolve() / approval_relpath(
        _ISSUE, _FROM, _TO
    )
