# URN: test:observe-and-correct:observer-runtime-and-rules:P001-UNIT-003-attach-prints-recent-observations
# Acceptance: acc:observe-and-correct:P001-UNIT-003-attach-prints-recent-observations
# WMBT: wmbt:observe-and-correct:P001
# Phase: RED
# Layer: application
"""P001-UNIT-003 — `atdd observer attach --agent-id <id>` prints recent
observations for the named agent including rule_id, timestamp, and
correction_text per observation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _write_correction(agent_dir: Path, **fields) -> None:
    base = {
        "agent_id": "agent-A",
        "rule_id": "coach.orchestration.read-only-git-diagnostics",
        "severity": 3,
        "disposition": "advisory",
        "correction_text": "stub",
        "injection_method": "cli-return",
        "issued_at": "2026-05-09T13:45:02Z",
    }
    base.update(fields)
    (agent_dir / "corrections.jsonl").parent.mkdir(parents=True, exist_ok=True)
    with (agent_dir / "corrections.jsonl").open("a") as fh:
        fh.write(json.dumps(base, sort_keys=True))
        fh.write("\n")


def test_attach_prints_rule_id_timestamp_and_correction_text(tmp_path, capsys):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)

    _write_correction(
        agent_dir,
        rule_id="coach.orchestration.read-only-git-diagnostics",
        correction_text="first thing to fix",
        issued_at="2026-05-09T10:00:00Z",
    )
    _write_correction(
        agent_dir,
        rule_id="coach.orchestration.test-runner-invocations",
        correction_text="second thing to fix",
        issued_at="2026-05-09T10:01:00Z",
    )

    rc = observer.cmd_attach(agent_id="agent-A", runtime_dir=runtime)
    assert rc == 0
    captured = capsys.readouterr().out
    assert "coach.orchestration.read-only-git-diagnostics" in captured
    assert "coach.orchestration.test-runner-invocations" in captured
    assert "first thing to fix" in captured
    assert "second thing to fix" in captured
    assert "2026-05-09T10:00:00Z" in captured
    assert "2026-05-09T10:01:00Z" in captured


def test_attach_no_corrections_does_not_crash(tmp_path, capsys):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    rc = observer.cmd_attach(agent_id="agent-missing", runtime_dir=runtime)
    assert rc == 0
    # Some informative line printed to stdout or stderr — we only require
    # the call not to crash and to return 0.


def test_attach_respects_limit(tmp_path, capsys):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)

    for i in range(5):
        _write_correction(
            agent_dir,
            correction_text=f"line-{i}",
            issued_at=f"2026-05-09T10:0{i}:00Z",
        )

    rc = observer.cmd_attach(agent_id="agent-A", runtime_dir=runtime, limit=2)
    assert rc == 0
    out = capsys.readouterr().out
    assert "line-3" in out and "line-4" in out
    assert "line-0" not in out
    assert "line-1" not in out
