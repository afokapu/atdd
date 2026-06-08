# URN: test:observe-and-correct:observer-runtime-and-rules:M002-UNIT-001-rule-06-fires-above-threshold
# Acceptance: acc:observe-and-correct:M002-UNIT-001-rule-06-fires-above-threshold
# WMBT: wmbt:observe-and-correct:M002
# Phase: GREEN
# Layer: application
"""M002-UNIT-001 — A simulated `claude --print-context-status` reading
above 400k tokens fires rule `06-token-threshold` with the §8.3
correction text `Approaching context limit. Run /compact.`; the
correction reaches the agent via the cli-return injection path.

Issue #507 (L3). Spec: `atdd-coach-spec-v9.md` §8.3.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


SPEC_CORRECTION_TEXT = "Approaching context limit. Run /compact."


def _write_rule_yaml(rules_dir: Path) -> Path:
    """Mirror the canonical rule shipped at .atdd/observer/rules/06-token-threshold.yaml."""
    rules_dir.mkdir(parents=True, exist_ok=True)
    rule_path = rules_dir / "06-token-threshold.yaml"
    rule_path.write_text(
        """\
rule_id: "06-token-threshold"
correction_text: "Approaching context limit. Run /compact."
trigger:
  type: token_threshold
injection_method: cli-return
severity: 3
disposition: advisory
absorbed_module: "src/atdd/coach/commands/token_threshold.py"
"""
    )
    return rule_path


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def test_rule_06_fires_when_token_count_above_default_threshold(tmp_path: Path):
    """A reading above the default 400k threshold fires rule 06."""
    from atdd.coach.commands import observer

    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    _write_rule_yaml(rules_dir)

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()
    assert obs.registry.rules, (
        "rule 06-token-threshold must load from .atdd/observer/rules/"
    )

    # Synthetic reading well above 400k.
    with patch(
        "atdd.coach.commands.token_threshold.read_token_count",
        return_value=450_000,
    ):
        with patch(
            "atdd.coach.commands.token_threshold.load_token_alert_threshold",
            return_value=400_000,
        ):
            corrections = obs.scan_once()

    assert len(corrections) == 1, "rule 06 must fire exactly once above threshold"
    cor = corrections[0]
    assert cor.correction_text == SPEC_CORRECTION_TEXT, (
        "Correction text must be the §8.3 spec literal"
    )
    assert cor.injection_method == "cli-return", (
        "Default injection_method per L1 / spec §8.2 path 1"
    )

    # cli-return path persisted the correction to <agent_dir>/cli-return.jsonl.
    cli_return_path = agent_dir / "cli-return.jsonl"
    assert cli_return_path.exists(), (
        "cli-return injection path must write to <agent_dir>/cli-return.jsonl"
    )
    records = _read_jsonl(cli_return_path)
    assert len(records) == 1
    assert records[0]["correction_text"] == SPEC_CORRECTION_TEXT


def test_rule_06_does_not_fire_when_token_count_below_threshold(tmp_path: Path):
    """A reading below 400k must NOT fire rule 06."""
    from atdd.coach.commands import observer

    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    _write_rule_yaml(rules_dir)

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()

    with patch(
        "atdd.coach.commands.token_threshold.read_token_count",
        return_value=100_000,
    ):
        with patch(
            "atdd.coach.commands.token_threshold.load_token_alert_threshold",
            return_value=400_000,
        ):
            corrections = obs.scan_once()

    assert corrections == [], "rule 06 must not fire below threshold"


def test_rule_06_does_not_fire_when_token_count_unavailable(tmp_path: Path):
    """A None reading (binary missing / parse failure) must NOT fire rule 06.

    Contract: `check_token_threshold(None, ...)` — unknown count → no alert.
    """
    from atdd.coach.commands import observer

    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    _write_rule_yaml(rules_dir)

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()

    with patch(
        "atdd.coach.commands.token_threshold.read_token_count",
        return_value=None,
    ):
        with patch(
            "atdd.coach.commands.token_threshold.load_token_alert_threshold",
            return_value=400_000,
        ):
            corrections = obs.scan_once()

    assert corrections == [], (
        "rule 06 must treat None reading as 'unknown' and not fire"
    )
