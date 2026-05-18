# URN: test:integration-hardening:coach-resume-wiring:E009-INTEGRATION-001-resume-invokes-transition-action
# Acceptance: acc:integration-hardening:E009-INTEGRATION-001-resume-invokes-transition-action
# WMBT: wmbt:integration-hardening:E009
# Phase: RED
# Layer: integration
"""E009-INTEGRATION-001 — the coach.py resume path invokes a real
``transition_action`` once per pending transition.

The fix wires ``ResumeRunner`` (constructed in the ``atdd coach --resume``
path) with a genuine ``transition_action``. This test injects a *recording*
fake transition_action through the resume path and asserts every pending
transition for the reconstructed issue dispatches a call carrying
``(issue, src, dst)``. Today coach.py builds ``ResumeRunner`` with no
``transition_action`` (defaults to ``None``) and offers no injection point,
so this test fails until the resume path is wired.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]

RUN_ID = "coach-run-734-int-001"


def _seed(writer, *, issue: int, src: str, dst: str, ts: str) -> None:
    writer.append({
        "decision_id": f"{RUN_ID}:#{issue}:{src}->{dst}",
        "timestamp": ts,
        "coach_run_id": RUN_ID,
        "issue_number": issue,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": src, "target_phase": dst},
        "outcome": {"transitioned": True, "new_phase": dst},
    })


def test_resume_invokes_transition_action_per_pending_transition(tmp_path):
    """A resumed SMOKE issue invokes transition_action for SMOKE→REFACTOR
    and REFACTOR→COMPLETE — call count >= 1, each call (issue, src, dst)."""
    from atdd.coach.commands.coach import run
    from atdd.coach.commands.durability import DecisionWriter

    runtime_dir = tmp_path / ".atdd" / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)
    # Reconstruct issue 999 to phase SMOKE — pending: REFACTOR, COMPLETE.
    _seed(writer, issue=999, src="INIT", dst="PLANNED", ts="2026-05-17T10:00:00Z")
    _seed(writer, issue=999, src="PLANNED", dst="RED", ts="2026-05-17T10:01:00Z")
    _seed(writer, issue=999, src="RED", dst="GREEN", ts="2026-05-17T10:02:00Z")
    _seed(writer, issue=999, src="GREEN", dst="SMOKE", ts="2026-05-17T10:03:00Z")

    recorded: list[tuple[int, str, str]] = []

    def recording_action(issue: int, src: str, dst: str) -> dict:
        recorded.append((issue, src, dst))
        return {"transitioned": True, "new_phase": dst}

    rc = run(
        issue_numbers=[999],
        dry_run=False,
        resume=RUN_ID,
        _runtime_dir_override=runtime_dir,
        _transition_action_override=recording_action,
    )

    assert rc == 0, f"resume run must succeed; rc={rc}"
    assert len(recorded) >= 1, (
        f"the resume path did not invoke transition_action — it paper-walked "
        f"the remaining phases without orchestration; recorded={recorded}"
    )
    assert (999, "SMOKE", "REFACTOR") in recorded, (
        f"the pending SMOKE→REFACTOR transition was not dispatched; "
        f"recorded={recorded}"
    )
    assert (999, "REFACTOR", "COMPLETE") in recorded, (
        f"the pending REFACTOR→COMPLETE transition was not dispatched; "
        f"recorded={recorded}"
    )
    for call in recorded:
        issue, src, dst = call
        assert issue == 999, f"call must carry the issue number; got {call}"
        assert isinstance(src, str) and src, f"call must carry a source phase; got {call}"
        assert isinstance(dst, str) and dst, f"call must carry a destination phase; got {call}"
