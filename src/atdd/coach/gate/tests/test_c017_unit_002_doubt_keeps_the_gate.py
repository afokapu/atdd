# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C017-UNIT-002-doubt-keeps-the-gate
# Acceptance: acc:govern-lifecycle:C017-UNIT-002-doubt-keeps-the-gate
# WMBT: wmbt:govern-lifecycle:C017
# Phase: RED
# Layer: application
"""C017-UNIT-002 — only a positive read of `agent` lifts the token.

The failure mode this guards is a gate that opens on uncertainty. Lifting the
requirement is a decision that must be POSITIVELY read from the machine; an
unreadable machine, a phase that declares nothing, or any other value all keep
the token demanded. Fail-closed, matching `phase_edges`' refusal to carry a
hardcoded fallback phase list for the same reason.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from atdd.coach.gate import approval_check as mod
from atdd.coach.gate.decision import GateContext, GateVerdict


def _ctx(tmp_path: Path) -> GateContext:
    return GateContext(
        issue_number=4242, from_phase="SMOKE", to_phase="REFACTOR", worktree=tmp_path
    )


@pytest.mark.parametrize("reading", [None, "operator", "", "AGENT-ish", "  agent  "])
def test_anything_but_agent_keeps_the_token_demanded(tmp_path, monkeypatch, reading):
    monkeypatch.setattr(mod, "_declared_autonomy", lambda _phase: reading)

    result = mod.ApprovalTokenGateCheck().run(_ctx(tmp_path))

    assert result.verdict == GateVerdict.FAIL, (
        f"autonomy read as {reading!r} is not a positive `agent`, so the token "
        f"must still be demanded; got {result.verdict}"
    )


def test_an_unreadable_machine_keeps_the_gate_and_is_reported(tmp_path, monkeypatch, caplog):
    def _boom(_phase):
        raise OSError("phase machine unreadable")

    monkeypatch.setattr(mod, "_declared_autonomy", _boom)

    with caplog.at_level(logging.WARNING):
        result = mod.ApprovalTokenGateCheck().run(_ctx(tmp_path))

    assert result.verdict == GateVerdict.FAIL, (
        "an unreadable machine must not open the gate; the one moment the "
        f"convention cannot be read is the moment to keep it shut, got {result.verdict}"
    )
    assert caplog.records, (
        "the read failure must be reported, not swallowed "
        "(coder.logging.coach-silent-swallow)"
    )
