# URN: test:govern-lifecycle:operator-approval-token-gate:R010-INTEGRATION-001-control-root-token-satisfies-gate-from-child-worktree
# Acceptance: acc:govern-lifecycle:R010-INTEGRATION-001-control-root-token-satisfies-gate-from-child-worktree
# WMBT: wmbt:govern-lifecycle:R010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""R010-INTEGRATION-001 — a Control-Root token satisfies the gate from a child worktree.

The real ``ApprovalTokenGateCheck`` is run against a ``GateContext`` whose
``worktree`` is a CHILD worktree — exactly what ``IssueLifecycle._transition_gate``
hands it (``self.target_dir``, i.e. ``target_dir or Path.cwd()``). A valid
operator-signed token written under the SHARED Control Root must make the check
pass; before #1376 the check joined ``approval_relpath`` onto ``ctx.worktree``
and could not see it.

The verdict is read off ``GateCheckResult`` — passed / rule_id / message — never
off a printed line (#865/#1020 anti-theater). The negative arrangement asserts
the child-worktree path is EMPTY while the check still passes, which is what
makes this a test of the resolution and not merely of the token format.

RED state: ``approval_check`` computes ``ctx.worktree / rel``, so the
Control-Root token is invisible and the passing arrangement fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.gate.approval import approval_relpath, build_token
from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.approval_paths import approval_control_root
from atdd.coach.gate.decision import GateContext

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"
_ISSUE, _FROM, _TO = 999999, "PLANNED", "RED"
_RULE_ID = "govern-lifecycle.E050.operator-approval-required"


@pytest.fixture
def nested_worktree(tmp_path: Path):
    """A child worktree nested under an initialized Control Root (see R010-UNIT-001)."""
    control_root = tmp_path / "project"
    (control_root / ".atdd" / "state").mkdir(parents=True)
    child = control_root / "feat-some-worktree"
    child.mkdir()
    # Precondition: the child really does resolve UP to the parent Control Root.
    assert approval_control_root(child) == control_root.resolve()
    return control_root, child


def _write_token(base: Path) -> Path:
    token_path = base / approval_relpath(_ISSUE, _FROM, _TO)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(
        json.dumps(
            build_token(
                _ISSUE, _FROM, _TO,
                approved_by="operator",
                approved_at="2026-08-03T00:00:00+00:00",
                key=_KEY,
            )
        )
    )
    return token_path


def _ctx(worktree: Path) -> GateContext:
    return GateContext(
        issue_number=_ISSUE, from_phase=_FROM, to_phase=_TO, worktree=worktree
    )


def test_control_root_token_passes_the_gate_from_a_child_worktree(nested_worktree):
    """Arrangement (a): the token lives at the Control Root; the gate finds it."""
    control_root, child = nested_worktree
    _write_token(control_root)
    # The pre-#1376 lookup location is EMPTY — so a pass here can only come from
    # Control-Root resolution, not from the worktree-local path.
    assert not (child / approval_relpath(_ISSUE, _FROM, _TO)).exists()

    result = ApprovalTokenGateCheck(signing_key=_KEY).run(_ctx(child))

    assert result.passed is True
    assert result.rule_id == _RULE_ID


def test_no_token_anywhere_fails_closed_with_the_produce_hint(nested_worktree):
    """Arrangement (b): absent from both locations -> FAIL naming relpath + produce hint."""
    _control_root, child = nested_worktree

    result = ApprovalTokenGateCheck(signing_key=_KEY).run(_ctx(child))

    assert result.passed is False
    assert result.rule_id == _RULE_ID
    assert str(approval_relpath(_ISSUE, _FROM, _TO)) in result.message
    assert f"atdd coach approve {_ISSUE} --transition {_FROM}->{_TO}" in result.message


def test_legacy_worktree_local_token_still_passes_the_gate(nested_worktree):
    """Back-compat: a token dropped worktree-local before #1376 is still honored."""
    control_root, child = nested_worktree
    _write_token(child)
    assert not (control_root / approval_relpath(_ISSUE, _FROM, _TO)).exists()

    result = ApprovalTokenGateCheck(signing_key=_KEY).run(_ctx(child))

    assert result.passed is True
    assert result.rule_id == _RULE_ID


def test_scope_isolation_survives_the_move(nested_worktree):
    """A Control-Root PLANNED->RED token does NOT unlock REFACTOR->COMPLETE.

    REFACTOR->COMPLETE rather than RED->GREEN since #1798: RED is declared `autonomy: agent`, so the approval check is NOT_APPLICABLE there and the isolation this asserts could no longer be observed on that edge.

    Moving the base must not weaken the scope binding the token already had:
    the relpath is per-transition, and verify_token still checks the signed scope.
    """
    control_root, child = nested_worktree
    _write_token(control_root)

    other = GateContext(
        issue_number=_ISSUE, from_phase="REFACTOR", to_phase="COMPLETE", worktree=child
    )
    assert ApprovalTokenGateCheck(signing_key=_KEY).run(other).passed is False


def test_forged_signature_under_the_control_root_still_fails_closed(nested_worktree):
    """The move changes WHERE the token is read, not WHETHER its signature is checked."""
    control_root, child = nested_worktree
    token_path = _write_token(control_root)
    forged = json.loads(token_path.read_text())
    forged["signature"] = "0" * 64
    token_path.write_text(json.dumps(forged))

    result = ApprovalTokenGateCheck(signing_key=_KEY).run(_ctx(child))

    assert result.passed is False
    assert "signature" in result.message
