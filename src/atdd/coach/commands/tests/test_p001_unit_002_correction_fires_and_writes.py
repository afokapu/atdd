# URN: test:observe-and-correct:observer-runtime-and-rules:P001-UNIT-002-correction-fires-and-writes
# Acceptance: acc:observe-and-correct:P001-UNIT-002-correction-fires-and-writes
# WMBT: wmbt:observe-and-correct:P001
# Phase: RED
# Layer: application
"""P001-UNIT-002 — A simulated detection rule fires and writes a
correction record to `.atdd/runtime/agents/<id>/corrections.jsonl`
validating against `correction.schema.json`; the default
`injection_method` is `cli-return` per §8.2 path 1.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

import atdd

pytestmark = [pytest.mark.platform]

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
CORRECTION_SCHEMA = (
    ATDD_PKG_DIR / "coach" / "schemas" / "correction.schema.json"
)


def _schema() -> dict:
    return json.loads(CORRECTION_SCHEMA.read_text())


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def test_observer_writes_schema_valid_correction_when_rule_fires(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)
    (agent_dir / "output.log").write_text("PROHIBITED-TOKEN\n")

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=None,
    )

    fired = observer.ObserverRule(
        rule_id="coach.observer.bash-read-only-git-diagnostics",
        predicate=lambda ctx: any("PROHIBITED-TOKEN" in line for line in ctx.log_lines),
        correction_text="Do not emit PROHIBITED-TOKEN.",
        severity=3,
        disposition="advisory",
    )
    obs.registry.add_rule(fired)

    corrections = obs.scan_once()
    assert len(corrections) == 1, "the synthetic rule must fire once"

    cor_path = agent_dir / "corrections.jsonl"
    assert cor_path.exists(), "scan_once must persist the correction"
    records = _read_jsonl(cor_path)
    assert len(records) == 1
    rec = records[0]

    schema = _schema()
    jsonschema.validate(rec, schema)

    assert rec["agent_id"] == "agent-A"
    assert rec["rule_id"] == "coach.observer.bash-read-only-git-diagnostics"
    assert rec["injection_method"] == "cli-return", (
        "Default injection_method must be cli-return per spec §8.2 path 1"
    )
    assert rec["correction_text"] == "Do not emit PROHIBITED-TOKEN."
    assert rec["severity"] == 3
    assert rec["disposition"] == "advisory"


def test_correction_dataclass_default_injection_method_is_cli_return():
    """Per spec §8.2, the default observer injection path is cli-return."""
    from atdd.coach.commands import observer

    c = observer.Correction(
        agent_id="agent-A",
        rule_id="coach.observer.bash-read-only-git-diagnostics",
        severity=3,
        disposition="advisory",
        correction_text="hi",
    )
    assert c.injection_method == "cli-return"


def test_observer_does_not_fire_when_predicate_returns_false(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)
    (agent_dir / "output.log").write_text("nothing notable here\n")

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=None,
    )
    obs.registry.add_rule(
        observer.ObserverRule(
            rule_id="coach.observer.bash-read-only-git-diagnostics",
            predicate=lambda ctx: False,
            correction_text="should not fire",
        )
    )
    corrections = obs.scan_once()
    assert corrections == []
    assert not (agent_dir / "corrections.jsonl").exists() or _read_jsonl(
        agent_dir / "corrections.jsonl"
    ) == []
