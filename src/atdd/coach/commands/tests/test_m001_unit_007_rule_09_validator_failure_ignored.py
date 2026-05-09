# URN: test:observe-and-correct:observer-runtime-and-rules:M001-UNIT-007-rule-09-validator-failure-ignored
# Acceptance: acc:observe-and-correct:M001-UNIT-007-rule-09-validator-failure-ignored
# WMBT: wmbt:observe-and-correct:M001
# Phase: RED
# Layer: application
"""M001-UNIT-007 — Rule `09-validator-failure-ignored`.

Issue #506 (L2). Spec: `atdd-coach-spec-v9.md` §8.3, §6.3, §7.6.

Fires when a tier-1 validator failed on a prior commit and the agent
commits again without addressing the cited rule_ids. The correction
text enumerates the unaddressed rule_ids and their `fix_hint`s pulled
from `bind_rule()`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
RULE_PATH = REPO_ROOT / ".atdd" / "observer" / "rules" / "09-validator-failure-ignored.yaml"


def _load_rule():
    from atdd.coach.commands import observer
    import yaml

    payload = yaml.safe_load(RULE_PATH.read_text(encoding="utf-8"))
    return observer._build_rule_from_yaml(payload, source_path=RULE_PATH)


def test_rule_yaml_exists_and_binds_to_canonical_rule_id():
    rule = _load_rule()
    assert rule.rule_id == "coach.observer.validator-failure-ignored"


def test_fires_on_recommit_without_addressing_prior_violations():
    from atdd.coach.commands import observer

    rule = _load_rule()
    # Use a real registered rule_id so fix_hint resolves via bind_rule().
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        prior_violations=(
            {"rule_id": "coach.commit-trailers.phase-required"},
            {"rule_id": "coach.commit-trailers.issue-required"},
        ),
        addressed_rule_ids=(),  # nothing addressed in the new commit
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None
    # Both unaddressed rule_ids must appear in the correction text.
    assert "coach.commit-trailers.phase-required" in correction.correction_text
    assert "coach.commit-trailers.issue-required" in correction.correction_text


def test_correction_includes_fix_hints_from_bind_rule():
    from atdd.coach.commands import observer
    from atdd.coach.utils.rule_binding import bind_rule

    rule = _load_rule()
    rid = "coach.commit-trailers.phase-required"
    expected_hint = bind_rule(rid).fix_hint
    assert expected_hint, (
        "test fixture invariant: the chosen rule_id must have a fix_hint registered"
    )
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        prior_violations=({"rule_id": rid},),
        addressed_rule_ids=(),
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None
    # A non-trivial slice of the canonical fix_hint must appear in the text.
    snippet = expected_hint.splitlines()[0].strip()
    assert snippet[:20] in correction.correction_text


def test_does_not_fire_when_new_commit_addresses_all_prior_violations():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        prior_violations=(
            {"rule_id": "coach.commit-trailers.phase-required"},
        ),
        addressed_rule_ids=("coach.commit-trailers.phase-required",),
    )
    assert rule.evaluate(ctx, agent_id="agent-A") is None


def test_does_not_fire_when_no_prior_violations():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(agent_id="agent-A")
    assert rule.evaluate(ctx, agent_id="agent-A") is None
