# URN: test:observe-and-correct:observer-runtime-and-rules:M001-UNIT-006-rule-08-reviewer-edit-attempt
# Acceptance: acc:observe-and-correct:M001-UNIT-006-rule-08-reviewer-edit-attempt
# WMBT: wmbt:observe-and-correct:M001
# Phase: RED
# Layer: application
"""M001-UNIT-006 — Rule `08-reviewer-edit-attempt`.

Issue #506 (L2). Spec: `atdd-coach-spec-v9.md` §8.3.

Fires when a reviewer-persona agent's output mentions edits or commits.
Correction asserts the no-write contract for reviewers.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
RULE_PATH = REPO_ROOT / ".atdd" / "observer" / "rules" / "08-reviewer-edit-attempt.yaml"


def _load_rule():
    from atdd.coach.commands import observer
    import yaml

    payload = yaml.safe_load(RULE_PATH.read_text(encoding="utf-8"))
    return observer._build_rule_from_yaml(payload, source_path=RULE_PATH)


def test_rule_yaml_exists_and_binds_to_canonical_rule_id():
    rule = _load_rule()
    assert rule.rule_id == "coach.observer.reviewer-edit-attempt"


def test_fires_on_reviewer_persona_mentioning_edit():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="reviewer-1",
        log_lines=("I will edit src/foo.py to fix the bug.",),
        persona="reviewer",
    )
    correction = rule.evaluate(ctx, agent_id="reviewer-1")
    assert correction is not None
    assert correction.correction_text == "You are a Reviewer. You may not edit or commit."


def test_fires_on_reviewer_persona_mentioning_commit():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="reviewer-1",
        log_lines=("Going to commit this fix now.",),
        persona="reviewer",
    )
    correction = rule.evaluate(ctx, agent_id="reviewer-1")
    assert correction is not None


def test_does_not_fire_for_non_reviewer_persona_with_same_output():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="coder-1",
        log_lines=(
            "I will edit src/foo.py to fix the bug.",
            "Going to commit this fix now.",
        ),
        persona="coder",
    )
    assert rule.evaluate(ctx, agent_id="coder-1") is None


def test_does_not_fire_for_reviewer_persona_with_no_edit_or_commit_mention():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="reviewer-1",
        log_lines=("LGTM, the diff looks consistent with the AC list.",),
        persona="reviewer",
    )
    assert rule.evaluate(ctx, agent_id="reviewer-1") is None
