# URN: test:integration-hardening:coach-cold-start-wiring:E002-INTEGRATION-003-cold-start-then-resume-reconstructs
# Acceptance: acc:integration-hardening:E002-INTEGRATION-003-cold-start-then-resume-reconstructs
# WMBT: wmbt:integration-hardening:E002
# Phase: RED
# Layer: integration
"""E002-INTEGRATION-003 — decisions.jsonl written by cold-start is valid for resume.

Per R4 (issue #645): cold-start and --resume share the same decisions.jsonl.
After cold-start writes the INIT→PLANNED record, ResumeRunner.reconstruct()
must return {issue_number: 'PLANNED'}.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _noop_mx():
    class _Mx:
        name = "fake"
        def new_workspace(self, cwd, command, name=None): return "workspace:1"
        def new_surface(self, **kw): return "surface:1"
        def new_persona_surface(self, cwd=None, command=None, name=None, *,
                                observer_runtime_root="", observer_agent_id="",
                                observer_name="", observer_command="", **_):
            persona_ref = self.new_surface(cwd=cwd, command=command, name=name)
            try:
                self.new_surface(cwd=cwd, command=observer_command, name=observer_name)
            except Exception:
                pass
            return persona_ref
        def rename(self, ref, name): pass
        def read_screen(self, ref, lines=50): return ""
        def send(self, ref, text): pass
        def send_key(self, ref, key): pass
        def list_workspaces(self): return []
        def close(self, ref): pass
    return _Mx()


def test_cold_start_decisions_are_resume_compatible(tmp_path, monkeypatch):
    """ResumeRunner.reconstruct() returns {issue: 'PLANNED'} from cold-start decisions."""
    from atdd.coach.commands.coach import run
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod
    from atdd.coach.commands.resume import ResumeRunner
    from atdd.coach.commands.durability import DecisionWriter

    wt = tmp_path / "wt"
    wt.mkdir()
    runtime_dir = tmp_path / ".atdd" / "runtime"

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_dir)
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: _noop_mx())

    run_id_holder: list[str] = []

    original_run = run

    rc = run(
        issue_numbers=[645],
        dry_run=False,
        resume=None,
        _runtime_dir_override=runtime_dir,
        _max_loop_events=0,
        _run_id_sink=run_id_holder,
    )
    assert rc == 0

    # Verify decisions.jsonl was written
    decisions_path = runtime_dir / "coach" / "decisions.jsonl"
    assert decisions_path.exists()

    # Extract the run_id from the decisions file
    records = [json.loads(line) for line in decisions_path.read_text().splitlines() if line.strip()]
    assert records
    run_id = records[0]["coach_run_id"]

    # Now use ResumeRunner to reconstruct
    writer = DecisionWriter(runtime_dir=runtime_dir)
    runner = ResumeRunner(runtime_dir=runtime_dir, run_id=run_id, decision_writer=writer)
    reconstructed = runner.reconstruct()

    assert 645 in reconstructed, f"Issue 645 not in reconstructed: {reconstructed}"
    assert reconstructed[645] == "PLANNED", (
        f"Expected PLANNED, got {reconstructed[645]!r}"
    )


def test_cold_start_run_id_is_stable_per_issue(tmp_path, monkeypatch):
    """All decisions for a single cold-start share the same coach_run_id."""
    from atdd.coach.commands.coach import run
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod

    wt = tmp_path / "wt"
    wt.mkdir()
    runtime_dir = tmp_path / ".atdd" / "runtime"

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_dir)
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: _noop_mx())

    run(
        issue_numbers=[645],
        dry_run=False,
        resume=None,
        _runtime_dir_override=runtime_dir,
        _max_loop_events=0,
    )

    decisions_path = runtime_dir / "coach" / "decisions.jsonl"
    records = [json.loads(line) for line in decisions_path.read_text().splitlines() if line.strip()]
    issue_records = [r for r in records if r.get("issue_number") == 645]
    assert issue_records
    run_ids = {r["coach_run_id"] for r in issue_records}
    assert len(run_ids) == 1, f"Expected single run_id for issue 645, got {run_ids}"
