# URN: test:observe-and-correct:observer-runtime-and-rules:M001-UNIT-001-rule-01-unstructured-question
# Acceptance: acc:observe-and-correct:M001-UNIT-001-rule-01-unstructured-question
# WMBT: wmbt:observe-and-correct:M001
# Phase: RED
# Layer: application
"""M001-UNIT-001 — Rule `01-unstructured-question`.

Issue #506 (L2). Spec: `atdd-coach-spec-v9.md` §8.3.

Fires on a free-form question phrasing in agent output that is NOT
preceded/wrapped by an `atdd agent ask --type ...` invocation. The
correction text instructs the agent to reformulate via the structured
CLI.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
RULE_PATH = REPO_ROOT / ".atdd" / "observer" / "rules" / "01-unstructured-question.yaml"


def _load_rule():
    from atdd.coach.commands import observer
    import yaml

    payload = yaml.safe_load(RULE_PATH.read_text(encoding="utf-8"))
    return observer._build_rule_from_yaml(payload, source_path=RULE_PATH)


def test_rule_yaml_exists_and_binds_to_canonical_rule_id():
    rule = _load_rule()
    assert rule.rule_id == "coach.observer.unstructured-question"


def test_fires_on_freeform_question_outside_atdd_agent_ask():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=("Should I rebase or merge here?",),
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None, "rule must fire on a free-form question"
    assert "atdd agent ask" in correction.correction_text


def test_does_not_fire_on_properly_formatted_atdd_agent_ask_invocation():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=(
            "atdd agent ask --type design 'Should I rebase or merge here?'",
        ),
    )
    assert rule.evaluate(ctx, agent_id="agent-A") is None, (
        "rule must NOT fire when the question is wrapped in `atdd agent ask`"
    )
