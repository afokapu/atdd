# URN: test:observe-and-correct:observer-runtime-and-rules:M001-UNIT-003-rule-03-completion-without-commit
# Acceptance: acc:observe-and-correct:M001-UNIT-003-rule-03-completion-without-commit
# WMBT: wmbt:observe-and-correct:M001
# Phase: RED
# Layer: application
"""M001-UNIT-003 — Rule `03-completion-claim-without-commit`.

Issue #506 (L2). Spec: `atdd-coach-spec-v9.md` §8.3.

Fires on a completion claim (`task complete`, `done`) when no
`commit_observed` event has been recorded since the claim. The
correction text states that completion was indicated but no commit was
detected.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
RULE_PATH = REPO_ROOT / ".atdd" / "observer" / "rules" / "03-completion-claim-without-commit.yaml"


def _load_rule():
    from atdd.coach.commands import observer
    import yaml

    payload = yaml.safe_load(RULE_PATH.read_text(encoding="utf-8"))
    return observer._build_rule_from_yaml(payload, source_path=RULE_PATH)


def test_rule_yaml_exists_and_binds_to_canonical_rule_id():
    rule = _load_rule()
    assert rule.rule_id == "coach.observer.completion-claim-without-commit"


def test_fires_on_completion_claim_without_commit_event():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=("All done — task complete.",),
        events=(),
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None
    assert "no commit" in correction.correction_text.lower()


def test_does_not_fire_when_completion_follows_a_recorded_commit():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=("All done — task complete.",),
        events=({"type": "commit_observed", "sha": "deadbeef"},),
    )
    assert rule.evaluate(ctx, agent_id="agent-A") is None
