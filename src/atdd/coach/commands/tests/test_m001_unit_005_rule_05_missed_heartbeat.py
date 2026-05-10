# URN: test:observe-and-correct:observer-runtime-and-rules:M001-UNIT-005-rule-05-missed-heartbeat
# Acceptance: acc:observe-and-correct:M001-UNIT-005-rule-05-missed-heartbeat
# WMBT: wmbt:observe-and-correct:M001
# Phase: RED
# Layer: application
"""M001-UNIT-005 — Rule `05-missed-heartbeat`.

Issue #506 (L2). Spec: `atdd-coach-spec-v9.md` §8.3 / §10
(`observer.process_silence_seconds`).

Fires when no `heartbeat.json` has been written for longer than the
configured threshold. Correction prompts the agent to call
`atdd agent heartbeat` after each significant action.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
RULE_PATH = REPO_ROOT / ".atdd" / "observer" / "rules" / "05-missed-heartbeat.yaml"


def _load_rule():
    from atdd.coach.commands import observer
    import yaml

    payload = yaml.safe_load(RULE_PATH.read_text(encoding="utf-8"))
    return observer._build_rule_from_yaml(payload, source_path=RULE_PATH)


def test_rule_yaml_exists_and_binds_to_canonical_rule_id():
    rule = _load_rule()
    assert rule.rule_id == "coach.observer.missed-heartbeat"


def test_fires_when_heartbeat_is_stale():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        now=1_000_000.0,
        heartbeat_mtime=1_000_000.0 - 600.0,  # 10 minutes ago
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None
    assert "atdd agent heartbeat" in correction.correction_text


def test_does_not_fire_when_heartbeat_is_fresh():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        now=1_000_000.0,
        heartbeat_mtime=1_000_000.0 - 5.0,
    )
    assert rule.evaluate(ctx, agent_id="agent-A") is None


def test_does_not_fire_when_no_heartbeat_observed_yet():
    """Absence of a heartbeat.json (e.g. agent just started) is NOT a
    fire condition — the rule only fires once a heartbeat existed and
    went stale."""
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(agent_id="agent-A", now=1_000_000.0, heartbeat_mtime=None)
    assert rule.evaluate(ctx, agent_id="agent-A") is None
