# URN: test:integration-hardening:coach-cold-start-wiring:E002-INTEGRATION-005-refactor-without-auto-merge-escalates
# Acceptance: acc:integration-hardening:E002-INTEGRATION-005-refactor-without-auto-merge-escalates
# WMBT: wmbt:integration-hardening:E002
# Phase: RED
# Layer: integration
"""E002-INTEGRATION-005 — without --auto-merge, REFACTOR stops and escalates.

When the cold-start driver reaches Phase.REFACTOR and --auto-merge is not set,
the driver must stop cleanly (return 0) and write an escalation to the
--escalation-channel so the operator knows manual intervention is required.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def _make_commit_event(issue_number: int, from_phase: str) -> dict:
    return {
        "event_type": "commit_observed",
        "agent_id": None,
        "timestamp": "2026-05-13T10:00:00.000000Z",
        "payload": {
            "sha": f"abc{from_phase}",
            "parent_sha": None,
            "branch": f"feat/issue-{issue_number}",
            "worktree_path": "/tmp/wt",
            "author": "test <test@example.com>",
            "trailers": {"Issue": str(issue_number), "Phase": from_phase},
        },
    }


def _noop_mx():
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


def test_refactor_without_auto_merge_writes_escalation(tmp_path, monkeypatch):
    """At REFACTOR with auto_merge=False, an escalation file is written."""
    from atdd.coach.commands.coach import run
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod

    wt = tmp_path / "wt"
    wt.mkdir()
    runtime_dir = tmp_path / ".atdd" / "runtime"
    escalation_log = tmp_path / "escalations.log"

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_dir)
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: _noop_mx())

    # Drive up to (but not including) COMPLETE
    events = [
        _make_commit_event(645, "PLANNED"),   # PLANNED → RED
        _make_commit_event(645, "RED"),        # RED → GREEN
        _make_commit_event(645, "GREEN"),      # GREEN → SMOKE
        _make_commit_event(645, "SMOKE"),      # SMOKE → REFACTOR
    ]

    rc = run(
        issue_numbers=[645],
        auto_merge=False,
        escalation_channel=f"file:{escalation_log}",
        dry_run=False,
        resume=None,
        _runtime_dir_override=runtime_dir,
        _injected_events={645: events},
    )

    assert rc == 0, f"Expected exit 0 on REFACTOR halt, got {rc}"
    assert escalation_log.exists(), (
        f"escalation file not created at {escalation_log}"
    )
    content = escalation_log.read_text()
    assert "645" in content or "REFACTOR" in content or "auto-merge" in content.lower(), (
        f"Expected REFACTOR/645/auto-merge in escalation; content={content!r}"
    )


def test_refactor_without_auto_merge_returns_zero(tmp_path, monkeypatch):
    """Without --auto-merge at REFACTOR, run() returns 0 (not an error exit)."""
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

    events = [
        _make_commit_event(645, "PLANNED"),
        _make_commit_event(645, "RED"),
        _make_commit_event(645, "GREEN"),
        _make_commit_event(645, "SMOKE"),
    ]

    rc = run(
        issue_numbers=[645],
        auto_merge=False,
        dry_run=False,
        resume=None,
        _runtime_dir_override=runtime_dir,
        _injected_events={645: events},
    )

    assert rc == 0
