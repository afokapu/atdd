# URN: test:observe-and-correct:observer-runtime-and-rules:M001-UNIT-002-rule-02-token-silence
# Acceptance: acc:observe-and-correct:M001-UNIT-002-rule-02-token-silence
# WMBT: wmbt:observe-and-correct:M001
# Phase: RED
# Layer: application
"""M001-UNIT-002 — Rule `02-token-silence`.

Issue #506 (L2). Spec: `atdd-coach-spec-v9.md` §8.3 / §10
(`observer.activity_silence_seconds` default 90s).

Fires when no tokens have been observed for longer than the configured
silence threshold. The correction reports the silence duration and
prompts `atdd agent escalate` if blocked.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
RULE_PATH = REPO_ROOT / ".atdd" / "observer" / "rules" / "02-token-silence.yaml"


def _load_rule():
    from atdd.coach.commands import observer
    import yaml

    payload = yaml.safe_load(RULE_PATH.read_text(encoding="utf-8"))
    return observer._build_rule_from_yaml(payload, source_path=RULE_PATH)


def test_rule_yaml_exists_and_binds_to_canonical_rule_id():
    rule = _load_rule()
    assert rule.rule_id == "coach.observer.token-silence"


def test_fires_when_silence_exceeds_threshold():
    from atdd.coach.commands import observer

    rule = _load_rule()
    # Default threshold per §10 is 90s; simulate 120s of silence.
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        now=2_000_000.0,
        last_token_at=2_000_000.0 - 120.0,
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None, "rule must fire on >90s silence"
    assert "120" in correction.correction_text, (
        "correction must report silence duration"
    )
    assert "atdd agent escalate" in correction.correction_text


def test_does_not_fire_below_threshold():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        now=2_000_000.0,
        last_token_at=2_000_000.0 - 30.0,
    )
    assert rule.evaluate(ctx, agent_id="agent-A") is None
