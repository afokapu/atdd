# URN: test:coach-ops:coach-dashboard:PLACEHOLDER-INTEGRATION-001-cli-dispatch
# WMBT: wmbt:coach-ops:PLACEHOLDER   # FIXME(transplant): set real WMBT id once the atdd issue exists
# Phase: RED
# Layer: application
"""`atdd coach dashboard` routes through coach.run_cli and reads the runtime."""
from __future__ import annotations

import json
from pathlib import Path

from atdd.coach.commands.coach_dashboard import run_dashboard


def _seed_run(runtime_dir: Path, run_id: str = "run-1") -> None:
    coach = runtime_dir / "coach"
    (coach / "1036").mkdir(parents=True)
    (coach / "decisions.jsonl").write_text(
        json.dumps(
            {
                "decision_id": "d1",
                "timestamp": "2026-06-10T19:50:00Z",
                "coach_run_id": run_id,
                "issue_number": 1036,
                "decision_type": "phase-transition",
                "inputs": {},
                "outcome": {"to_phase": "REFACTOR"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    # Real worker layout: agents/<role>-<issue>-<hash>/{manifest,events}.
    agent = runtime_dir / "agents" / "coder-1036-2c0f2794"
    agent.mkdir(parents=True)
    (agent / "manifest.json").write_text(
        json.dumps({"agent_id": "coder-1036-2c0f2794", "issue": 1036, "persona": "coder"}),
        encoding="utf-8",
    )
    (agent / "events.jsonl").write_text(
        json.dumps({"occurred_at": "2026-06-10T19:55:00Z"}) + "\n", encoding="utf-8"
    )


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
    assert "REFACTOR" in out
    assert "1 worker" in out


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
