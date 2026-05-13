# URN: test:integration-hardening:coach-cold-start-wiring:E002-INTEGRATION-002-cold-start-writes-decisions-jsonl
# Acceptance: acc:integration-hardening:E002-INTEGRATION-002-cold-start-writes-decisions-jsonl
# WMBT: wmbt:integration-hardening:E002
# Phase: RED
# Layer: integration
"""E002-INTEGRATION-002 — cold-start writes decisions.jsonl with INIT→PLANNED entry.

Per R4 (issue #645): cold-start MUST write decisions.jsonl on every transition
so that a Ctrl+C kill is recoverable via --resume.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_cold_start_writes_decisions_jsonl(tmp_path, monkeypatch):
    """INIT→PLANNED decision is appended before the spawn side-effect."""
    from atdd.coach.commands.coach import run
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod

    wt = tmp_path / "wt"
    wt.mkdir()
    runtime_dir = tmp_path / ".atdd" / "runtime"

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_dir)

    spawned: list[dict] = []

    def fake_resolve_mx(preferred=None):
        class _Mx:
            name = "fake"
            def new_workspace(self, cwd, command, name=None):
                spawned.append({"cwd": cwd, "cmd": command})
                return "workspace:1"
            def new_surface(self, **kw):
                spawned.append(kw)
                return "surface:1"
            def rename(self, ref, name): pass
            def read_screen(self, ref, lines=50): return ""
            def send(self, ref, text): pass
            def send_key(self, ref, key): pass
            def list_workspaces(self): return []
            def close(self, ref): pass
        return _Mx()

    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", fake_resolve_mx)

    rc = run(
        issue_numbers=[645],
        dry_run=False,
        resume=None,
        _runtime_dir_override=runtime_dir,
        _max_loop_events=0,
    )

    assert rc == 0
    decisions_path = runtime_dir / "coach" / "decisions.jsonl"
    assert decisions_path.exists(), f"decisions.jsonl not found at {decisions_path}"
    records = [json.loads(line) for line in decisions_path.read_text().splitlines() if line.strip()]
    assert records, "decisions.jsonl is empty"

    transition_records = [r for r in records if r.get("decision_type") == "phase-transition"]
    assert transition_records, "No phase-transition records in decisions.jsonl"

    init_to_planned = [
        r for r in transition_records
        if r.get("inputs", {}).get("current_phase") == "INIT"
        and r.get("inputs", {}).get("target_phase") == "PLANNED"
    ]
    assert init_to_planned, (
        f"No INIT→PLANNED transition record found; records={transition_records}"
    )


def test_decisions_jsonl_has_required_fields(tmp_path, monkeypatch):
    """Each decision record conforms to the coach-decision schema minimums."""
    from atdd.coach.commands.coach import run
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod

    wt = tmp_path / "wt"
    wt.mkdir()
    runtime_dir = tmp_path / ".atdd" / "runtime"

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_dir)

    def fake_resolve_mx(preferred=None):
        class _Mx:
            name = "fake"
            def new_workspace(self, cwd, command, name=None): return "workspace:1"
            def new_surface(self, **kw): return "surface:1"
            def rename(self, ref, name): pass
            def read_screen(self, ref, lines=50): return ""
            def send(self, ref, text): pass
            def send_key(self, ref, key): pass
            def list_workspaces(self): return []
            def close(self, ref): pass
        return _Mx()

    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", fake_resolve_mx)

    run(
        issue_numbers=[645],
        dry_run=False,
        resume=None,
        _runtime_dir_override=runtime_dir,
        _max_loop_events=0,
    )

    decisions_path = runtime_dir / "coach" / "decisions.jsonl"
    records = [json.loads(line) for line in decisions_path.read_text().splitlines() if line.strip()]
    for rec in records:
        assert "decision_id" in rec, f"missing decision_id: {rec}"
        assert "timestamp" in rec, f"missing timestamp: {rec}"
        assert "coach_run_id" in rec, f"missing coach_run_id: {rec}"
        assert "issue_number" in rec, f"missing issue_number: {rec}"
        assert "decision_type" in rec, f"missing decision_type: {rec}"
