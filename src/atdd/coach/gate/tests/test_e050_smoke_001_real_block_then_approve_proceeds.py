# URN: test:govern-lifecycle:operator-approval-token-gate:E050-SMOKE-001-real-cli-blocked-without-token-proceeds-after-coach-approve
# Acceptance: acc:govern-lifecycle:E050-SMOKE-001-real-cli-blocked-without-token-proceeds-after-coach-approve
# WMBT: wmbt:govern-lifecycle:E050
# Phase: SMOKE
# Layer: integration
# Smoke: true
# Assertion: behavioral
# Purpose: exercise the real registration -> registry -> decision -> token-file path with the real operator approve command, no mocks
"""E050-SMOKE-001 — block without token, proceed after the real `atdd coach approve`.

No fakes on the gate path: the real ``register_approval_checks`` registers the
real ``ApprovalTokenGateCheck`` into a real ``GateRegistry``; the real
``evaluate_transition_gate`` decides; and the token is produced by the REAL
operator command ``atdd coach approve`` (``approve_command.run``) writing a real
file under a real worktree. The gate reads the FILESYSTEM, never the cmux Feed —
so an absent operator BLOCKS and only the operator-signed token unblocks, exactly
the (issue, from, to) one. This is the production wiring the hermetic
integration tests stub at the issue-fetch boundary.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.approve_command import run as run_approve
from atdd.coach.gate.decision import GateContext, evaluate_transition_gate
from atdd.coach.gate.registrations import register_approval_checks
from atdd.coach.gate.registry import GateRegistry

pytestmark = [pytest.mark.platform]

_GATED_CONFIG = {"gate": {"transitions": {"PLANNED->RED": True}}}


def _ctx(worktree: Path) -> GateContext:
    return GateContext(
        issue_number=1017, from_phase="PLANNED", to_phase="RED", worktree=worktree
    )


def test_blocked_without_token_then_proceeds_after_real_approve(tmp_path: Path, monkeypatch):
    # Pin a deterministic operator signing key for the whole real path.
    monkeypatch.setenv("ATDD_APPROVAL_SIGNING_KEY", "smoke-operator-key")

    registry = GateRegistry()
    register_approval_checks(registry)  # real production registration

    # 1) No token on disk -> the real gate BLOCKS.
    blocked = evaluate_transition_gate(registry, _GATED_CONFIG, _ctx(tmp_path))
    assert blocked.proceed is False
    assert any(f.gate_id == "approval-token" for f in blocked.failures)

    # 2) The real operator command writes the real signed token into the worktree.
    rc = run_approve(["1017", "--transition", "PLANNED->RED", "--by", "alec"], target_dir=tmp_path)
    assert rc == 0
    assert (tmp_path / ".atdd/runtime/issue-1017/approvals/PLANNED-RED.json").exists()

    # 3) Same real gate now PROCEEDS — purely from the filesystem token, no Feed.
    proceeded = evaluate_transition_gate(registry, _GATED_CONFIG, _ctx(tmp_path))
    assert proceeded.proceed is True

    # 4) Scope isolation under the real path: the PLANNED->RED token does NOT
    #    unlock RED->GREEN (which the registration also gates a check on).
    next_ctx = GateContext(
        issue_number=1017, from_phase="RED", to_phase="GREEN", worktree=tmp_path
    )
    next_gated = {"gate": {"transitions": {"RED->GREEN": True}}}
    assert evaluate_transition_gate(registry, next_gated, next_ctx).proceed is False
