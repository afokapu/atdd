# URN: test:integration-hardening:coach-resume-wiring:E009-INTEGRATION-002-resume-spawns-pending-phase-persona
# Acceptance: acc:integration-hardening:E009-INTEGRATION-002-resume-spawns-pending-phase-persona
# WMBT: wmbt:integration-hardening:E009
# Phase: RED
# Layer: integration
"""E009-INTEGRATION-002 — ``atdd coach --resume`` spawns the pending-phase
persona via the same orchestration the cold-start path uses.

A run reconstructed mid-lifecycle (issue 999 at SMOKE) must, when the resume
path drives SMOKE→REFACTOR, spawn the coder persona. A ``FakeMultiplexer`` is
injected so no real cmux pane is created and every spawn is captured. Today
coach.py constructs ``ResumeRunner`` with ``transition_action=None``, so the
resume run is a pure paper walk — the multiplexer records zero spawns and
this test fails.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]

RUN_ID = "coach-run-734-int-002"


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


def test_resume_spawns_coder_persona_for_pending_smoke_phase(tmp_path, monkeypatch):
    """Resuming a SMOKE issue records at least one persona spawn (coder for
    SMOKE→REFACTOR) on the injected FakeMultiplexer — not a paper walk."""
    from atdd.coach.commands.coach import run
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod
    from atdd.coach.utils.multiplexer import FakeMultiplexer

    runtime_dir = tmp_path / ".atdd" / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)
    # Reconstruct issue 999 to phase SMOKE — the pending phase to drive is REFACTOR.
    _seed(writer, issue=999, src="INIT", dst="PLANNED", ts="2026-05-17T10:00:00Z")
    _seed(writer, issue=999, src="PLANNED", dst="RED", ts="2026-05-17T10:01:00Z")
    _seed(writer, issue=999, src="RED", dst="GREEN", ts="2026-05-17T10:02:00Z")
    _seed(writer, issue=999, src="GREEN", dst="SMOKE", ts="2026-05-17T10:03:00Z")

    fake_mx = FakeMultiplexer()
    wt = tmp_path / "wt"
    wt.mkdir()

    # Synthetic spawn dependencies so no real persona prompt / worktree is needed.
    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_dir)
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    rc = run(
        issue_numbers=[999],
        dry_run=False,
        resume=RUN_ID,
        _runtime_dir_override=runtime_dir,
        _max_loop_events=0,
    )

    assert rc == 0, f"resume run must succeed; rc={rc}"

    spawn_calls = [c for c in fake_mx.calls if c.get("op") in ("new_workspace", "new_surface")]
    assert len(spawn_calls) >= 1, (
        f"resuming a SMOKE issue must spawn the pending-phase persona; the "
        f"FakeMultiplexer recorded no spawn — the resume run is a paper walk. "
        f"calls={fake_mx.calls}"
    )

    coder_calls = [c for c in spawn_calls if "coder" in str(c.get("command") or "")]
    assert len(coder_calls) >= 1, (
        f"the SMOKE→REFACTOR transition must spawn the coder persona; "
        f"spawn calls={spawn_calls}"
    )
