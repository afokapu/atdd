# URN: test:observe-and-correct:observer-runtime-and-rules:P002-UNIT-004-observer-status-line-and-trace
# Acceptance: acc:observe-and-correct:P002-UNIT-004-observer-status-line-and-trace
# WMBT: wmbt:observe-and-correct:P002
# Phase: RED
# Layer: presentation
"""P002-UNIT-004 — `atdd observer run` must be operator-interpretable.

Issue #713 Layer 4: ``atdd observer run`` is a headless silent poll
loop. The observer tab shows the launch command and then nothing.

The observer must render a live status line (watched persona, loaded
rule count, last-scan timestamp, corrections-issued count) and let the
operator see what it ingested for a scan and which rules fired.

RED: these tests fail today — cmd_run prints nothing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_observer_run_renders_a_status_line(tmp_path: Path, capsys):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)
    persona_dir = runtime / "agents" / "planner-713-s"
    persona_dir.mkdir(parents=True)
    (persona_dir / "output.log").write_text("hello from the persona\n")

    rc = observer.cmd_run(
        agent_id="planner-713-s-observer",
        runtime_dir=runtime,
        rules_dir=rules_dir,
        once=True,
    )
    assert rc == 0
    out = capsys.readouterr().out

    assert "planner-713-s" in out, "status line must name the watched persona"
    assert "rule" in out.lower(), "status line must report the loaded rule count"
    assert "scan" in out.lower(), "status line must report the last-scan time"
    assert "correction" in out.lower(), (
        "status line must report the corrections-issued count"
    )


def test_operator_can_see_ingested_input_and_fired_rule(tmp_path: Path, capsys):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)
    persona_dir = runtime / "agents" / "planner-713-s"
    persona_dir.mkdir(parents=True)
    (persona_dir / "output.log").write_text("RING THE BELL now please\n")

    # A rule that fires on the persona's real output.
    (rules_dir / "50-bell.yaml").write_text(
        "rule_id: \"coach.orchestration.read-only-git-diagnostics\"\n"
        "trigger:\n"
        "  type: log_regex\n"
        "  pattern: \".*RING THE BELL.*\"\n"
        "correction_text: \"stop ringing the bell\"\n"
        "injection_method: \"cli-return\"\n"
        "severity: 3\n"
        "disposition: \"advisory\"\n"
    )

    rc = observer.cmd_run(
        agent_id="planner-713-s-observer",
        runtime_dir=runtime,
        rules_dir=rules_dir,
        once=True,
    )
    assert rc == 0
    out = capsys.readouterr().out

    assert "RING THE BELL" in out, (
        "operator must be able to see what the observer ingested this scan"
    )
    assert "coach.orchestration.read-only-git-diagnostics" in out, (
        "operator must be able to see which rule ids fired"
    )
