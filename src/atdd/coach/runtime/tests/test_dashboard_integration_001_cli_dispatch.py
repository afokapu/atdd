# URN: test:coach-ops:coach-dashboard:PLACEHOLDER-INTEGRATION-001-cli-dispatch
# WMBT: wmbt:coach-ops:PLACEHOLDER   # FIXME(transplant): set real WMBT id once the atdd issue exists
# Phase: RED
# Layer: application
"""`atdd coach dashboard` routes through coach.run_cli and reads the runtime."""
from __future__ import annotations

import json
from pathlib import Path

from atdd.coach.commands.coach_dashboard import run_dashboard


def _session(runtime_dir: Path, issue: int, agent_id: str, persona: str, phase: str) -> None:
    d = runtime_dir / "coach" / str(issue)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{agent_id}.session.json").write_text(
        json.dumps(
            {
                "issue": issue,
                "agent_id": agent_id,
                "persona": persona,
                "phase": phase,
                "spawned_at": "2026-06-10T19:48:00Z",
            }
        ),
        encoding="utf-8",
    )
    agent = runtime_dir / "agents" / agent_id
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "events.jsonl").write_text(
        json.dumps({"occurred_at": "2026-06-10T19:55:00Z"}) + "\n", encoding="utf-8"
    )


def _seed_run(runtime_dir: Path, run_id: str = "run-1036-test") -> None:
    # Authoritative run record: drives issue 1036.
    run_dir = runtime_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps({"run_id": run_id, "issue_number": 1036, "state": "RUNNING",
                    "current_phase": "GREEN"}),
        encoding="utf-8",
    )
    # One worker on the active issue, and a worker on an *inactive* issue that
    # must NOT appear in the default (current-run) scope.
    _session(runtime_dir, 1036, "coder-1036-2c0f2794", "coder", "green")
    _session(runtime_dir, 999, "planner-999-deadbeef", "planner", "init")


def test_no_runs_is_clean_exit(tmp_path, capsys):
    rc = run_dashboard([], runtime_dir=tmp_path / "runtime")
    assert rc == 0
    assert "No coach runs found" in capsys.readouterr().out


def test_dashboard_renders_seeded_worker(tmp_path, capsys):
    runtime = tmp_path / "runtime"
    _seed_run(runtime)
    rc = run_dashboard(["--width", "80"], runtime_dir=runtime)
    out = capsys.readouterr().out
    assert rc == 0
    assert "#1036" in out
    assert "GREEN" in out  # session phase "green" → GREEN
    assert "coder" in out


def test_default_scope_excludes_inactive_run_issues(tmp_path, capsys):
    runtime = tmp_path / "runtime"
    _seed_run(runtime)  # run drives #1036; #999 is an inactive issue on disk
    rc = run_dashboard(["--width", "80"], runtime_dir=runtime)
    out = capsys.readouterr().out
    assert rc == 0
    assert "#1036" in out and "1 worker" in out
    assert "#999" not in out


def test_all_scope_includes_inactive_run_issues(tmp_path, capsys):
    runtime = tmp_path / "runtime"
    _seed_run(runtime)
    rc = run_dashboard(["--all", "--width", "80"], runtime_dir=runtime)
    out = capsys.readouterr().out
    assert rc == 0
    assert "#1036" in out and "#999" in out
    assert "2 worker" in out


def test_explicit_run_id_from_runs_dir_is_accepted(tmp_path, capsys):
    runtime = tmp_path / "runtime"
    _seed_run(runtime)
    rc = run_dashboard(["--run-id", "run-1036-test", "--width", "80"], runtime_dir=runtime)
    assert rc == 0
    assert "#1036" in capsys.readouterr().out


def test_run_cli_routes_dashboard(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    from atdd.coach.commands import coach as coach_mod

    rc = coach_mod.run_cli(["dashboard"])
    assert rc == 0
    assert "No coach runs found" in capsys.readouterr().out


def test_unknown_run_id_errors(tmp_path, capsys):
    runtime = tmp_path / "runtime"
    _seed_run(runtime)
    rc = run_dashboard(["--run-id", "nope"], runtime_dir=runtime)
    assert rc == 1
    assert "not found" in capsys.readouterr().err
