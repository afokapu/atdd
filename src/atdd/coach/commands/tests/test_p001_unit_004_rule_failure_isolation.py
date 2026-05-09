# URN: test:observe-and-correct:observer-runtime-and-rules:P001-UNIT-004-rule-failure-isolation
# Acceptance: acc:observe-and-correct:P001-UNIT-004-rule-failure-isolation
# WMBT: wmbt:observe-and-correct:P001
# Phase: RED
# Layer: application
"""P001-UNIT-004 — A rule that raises an unhandled exception is caught,
logged with its rule_id, marked faulty for the remainder of the run, and
does NOT crash the observer or affect other rules' evaluation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def test_faulty_rule_is_caught_and_other_rules_still_fire(
    tmp_path: Path, capsys
):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)
    (agent_dir / "output.log").write_text("RING THE BELL\n")

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=None,
    )

    def boom(_ctx):
        raise RuntimeError("rule A is broken")

    rule_a = observer.ObserverRule(
        rule_id="coach.orchestration.read-only-git-diagnostics",
        predicate=boom,
        correction_text="should never be emitted",
    )
    rule_b = observer.ObserverRule(
        rule_id="coach.orchestration.test-runner-invocations",
        predicate=lambda ctx: any("RING THE BELL" in line for line in ctx.log_lines),
        correction_text="B fires",
    )
    obs.registry.add_rule(rule_a)
    obs.registry.add_rule(rule_b)

    corrections = obs.scan_once()
    rule_ids = [c.rule_id for c in corrections]
    assert (
        "coach.orchestration.test-runner-invocations" in rule_ids
    ), "Rule B must still fire after Rule A raises"
    assert (
        "coach.orchestration.read-only-git-diagnostics" not in rule_ids
    ), "Faulty rule A must not produce a correction"

    # Faulty rule recorded with its rule_id.
    assert (
        "coach.orchestration.read-only-git-diagnostics" in obs.registry.faulty_rules
    )

    # The observer process did not raise — confirmed by reaching this point.
    err = capsys.readouterr().err
    assert "coach.orchestration.read-only-git-diagnostics" in err, (
        "Faulty rule must be logged to stderr with its rule_id"
    )


def test_faulty_rule_remains_faulty_for_subsequent_scans(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)
    (agent_dir / "output.log").write_text("never matters\n")

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=None,
    )

    call_count = {"n": 0}

    def boom(_ctx):
        call_count["n"] += 1
        raise RuntimeError("always broken")

    obs.registry.add_rule(
        observer.ObserverRule(
            rule_id="coach.orchestration.read-only-git-diagnostics",
            predicate=boom,
            correction_text="x",
        )
    )

    obs.scan_once()
    obs.scan_once()
    obs.scan_once()

    # After the first failure the rule is marked faulty and skipped on
    # subsequent passes — predicate must be called exactly once.
    assert call_count["n"] == 1, (
        "Faulty rules must not be re-evaluated for the remainder of the run"
    )
