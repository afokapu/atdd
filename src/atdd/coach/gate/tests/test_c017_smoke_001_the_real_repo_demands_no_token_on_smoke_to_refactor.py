# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C017-SMOKE-001-the-real-repo-demands-no-token-on-smoke-to-refactor
# Acceptance: acc:govern-lifecycle:C017-SMOKE-001-the-real-repo-demands-no-token-on-smoke-to-refactor
# WMBT: wmbt:govern-lifecycle:C017
# Phase: RED
# Layer: integration
"""C017-SMOKE-001 — the real repo stops on no human at SMOKE->REFACTOR.

Against the repository's own committed machine and config, not fixtures. The
edge must stay listed in `gate.transitions` — that listing is what switches on
the #1602 evidence check, and removing it would revert that issue — while the
operator token it dragged along is no longer demanded.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.decision import GateContext, GateVerdict
from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo


@pytest.mark.platform
def test_the_real_repo_demands_no_token_on_smoke_to_refactor(tmp_path):
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; the committed machine is the subject")

    root = find_repo_root()
    cfg = yaml.safe_load((root / ".atdd" / "config.yaml").read_text()) or {}
    gated = ((cfg.get("gate") or {}).get("transitions")) or {}

    assert gated.get("SMOKE->REFACTOR") is True, (
        "SMOKE->REFACTOR must stay gated: that listing is what enables the #1602 "
        "smoke-execution evidence check. Removing it would revert #1602, which is "
        "why this issue lifts the token in the CHECK instead of the config."
    )

    check = ApprovalTokenGateCheck()
    agent_edge = check.run(
        GateContext(issue_number=4242, from_phase="SMOKE", to_phase="REFACTOR", worktree=tmp_path)
    )
    assert agent_edge.verdict == GateVerdict.NOT_APPLICABLE, (
        f"no operator stop should remain on SMOKE->REFACTOR; got {agent_edge.verdict}"
    )

    operator_edge = check.run(
        GateContext(issue_number=4242, from_phase="PLANNED", to_phase="RED", worktree=tmp_path)
    )
    assert operator_edge.verdict == GateVerdict.FAIL, (
        "PLANNED->RED is the single operator judgement gate and must be untouched; "
        f"got {operator_edge.verdict}"
    )
