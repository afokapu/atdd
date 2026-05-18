# URN: test:integration-hardening:coach-resume-wiring:E009-INTEGRATION-003-no-paper-fast-forward-on-block
# Acceptance: acc:integration-hardening:E009-INTEGRATION-003-no-paper-fast-forward-on-block
# WMBT: wmbt:integration-hardening:E009
# Phase: RED
# Layer: integration
"""E009-INTEGRATION-003 — a resume run that cannot complete a phase BLOCKs
and escalates; it never paper-stamps the failing phase or any later one.

When the pending SMOKE→REFACTOR transition cannot complete, the resume run
must BLOCK/escalate — write no ``phase-transition`` record for REFACTOR or
COMPLETE, and surface a block outcome (non-zero rc or an escalation entry).
Today coach.py wires ``transition_action=None``, so the resume path paper-
walks straight to COMPLETE regardless — this test fails until the resume
path dispatches a real action and honours its failure.
"""
from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.platform]

RUN_ID = "coach-run-734-int-003"


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


def _read_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_resume_blocks_without_paper_fast_forward_on_failed_phase(tmp_path, capsys):
    """A transition_action that fails on SMOKE→REFACTOR blocks the resume run:
    no REFACTOR or COMPLETE phase-transition record, and a block outcome."""
    from atdd.coach.commands.coach import run
    from atdd.coach.commands.durability import DecisionWriter

    runtime_dir = tmp_path / ".atdd" / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)
    # Reconstruct issue 999 to phase SMOKE — pending: REFACTOR, COMPLETE.
    _seed(writer, issue=999, src="INIT", dst="PLANNED", ts="2026-05-17T10:00:00Z")
    _seed(writer, issue=999, src="PLANNED", dst="RED", ts="2026-05-17T10:01:00Z")
    _seed(writer, issue=999, src="RED", dst="GREEN", ts="2026-05-17T10:02:00Z")
    _seed(writer, issue=999, src="GREEN", dst="SMOKE", ts="2026-05-17T10:03:00Z")

    esc_path = tmp_path / "escalations.log"

    def failing_action(issue: int, src: str, dst: str) -> dict:
        if (src, dst) == ("SMOKE", "REFACTOR"):
            raise RuntimeError(f"simulated BLOCK: #{issue} cannot complete SMOKE→REFACTOR")
        return {"transitioned": True, "new_phase": dst}

    rc = run(
        issue_numbers=[999],
        dry_run=False,
        resume=RUN_ID,
        escalation_channel=f"file:{esc_path}",
        _runtime_dir_override=runtime_dir,
        _transition_action_override=failing_action,
    )

    records = _read_jsonl(writer.path)
    targets = [(r.get("inputs") or {}).get("target_phase") for r in records
               if r.get("decision_type") == "phase-transition"]
    assert "REFACTOR" not in targets, (
        f"the failed SMOKE→REFACTOR transition was paper-stamped anyway; "
        f"target_phases={targets}"
    )
    assert "COMPLETE" not in targets, (
        f"a REFACTOR→COMPLETE record was written after a blocked phase — "
        f"the resume run paper-walked past the block; target_phases={targets}"
    )

    escalated = esc_path.exists() and esc_path.read_text().strip() != ""
    assert rc != 0 or escalated, (
        f"a blocked resume must surface a BLOCK/escalation outcome — non-zero "
        f"rc or an escalation entry; rc={rc}, escalation_written={escalated}"
    )

    out = capsys.readouterr().out
    assert "#999 → COMPLETE" not in out, (
        f"issue 999 must not be reported COMPLETE after a block; output:\n{out}"
    )
