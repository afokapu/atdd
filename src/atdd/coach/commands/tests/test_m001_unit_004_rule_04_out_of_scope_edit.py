# URN: test:observe-and-correct:observer-runtime-and-rules:M001-UNIT-004-rule-04-out-of-scope-edit
# Acceptance: acc:observe-and-correct:M001-UNIT-004-rule-04-out-of-scope-edit
# WMBT: wmbt:observe-and-correct:M001
# Phase: RED
# Layer: application
"""M001-UNIT-004 — Rule `04-out-of-scope-edit`.

Issue #506 (L2). Spec: `atdd-coach-spec-v9.md` §8.3 / §0.2 (the
`.atdd/` clause absorbed verbatim from babysit's ``detect_violation``).

Fires when:
  (a) a worktree change touches a file outside the WMBT target paths, or
  (b) a worktree change touches any path under `.atdd/` outside the
      allowlist (the absorbed babysit clause).

The correction names the offending path and instructs revert-or-escalate.
Behavior at parity with babysit's ``detect_violation`` `.atdd/` clause for
the absorbed cases.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
RULE_PATH = REPO_ROOT / ".atdd" / "observer" / "rules" / "04-out-of-scope-edit.yaml"


def _load_rule():
    from atdd.coach.commands import observer
    import yaml

    payload = yaml.safe_load(RULE_PATH.read_text(encoding="utf-8"))
    return observer._build_rule_from_yaml(payload, source_path=RULE_PATH)


def test_rule_yaml_exists_and_binds_to_canonical_rule_id():
    rule = _load_rule()
    assert rule.rule_id == "coach.observer.out-of-scope-edit"


def test_fires_on_change_outside_wmbt_target_paths():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/atdd/coach/commands/observer.py", "src/elsewhere/foo.py"),
        wmbt_target_paths=("src/atdd/coach/commands/",),
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None
    assert "src/elsewhere/foo.py" in correction.correction_text
    assert "revert" in correction.correction_text.lower() or "escalate" in correction.correction_text.lower()


def test_fires_on_atdd_hand_edit_outside_allowlist_absorbed_babysit_clause():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=(".atdd/manifest.yaml",),
        # WMBT scope intentionally permissive; the .atdd/ clause is independent.
        wmbt_target_paths=(".",),
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None, (
        "rule must fire on .atdd/ hand-edits outside the allowlist (babysit clause)"
    )
    assert ".atdd/manifest.yaml" in correction.correction_text


def test_does_not_fire_on_in_scope_change():
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/atdd/coach/commands/observer.py",),
        wmbt_target_paths=("src/atdd/coach/commands/",),
    )
    assert rule.evaluate(ctx, agent_id="agent-A") is None


def test_does_not_fire_on_atdd_allowlisted_observer_rules_subtree():
    """`.atdd/observer/rules/` is an allowlisted location for #L2 rule
    files — editing them must not trip the babysit clause."""
    from atdd.coach.commands import observer

    rule = _load_rule()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=(".atdd/observer/rules/01-unstructured-question.yaml",),
        wmbt_target_paths=(".",),
    )
    assert rule.evaluate(ctx, agent_id="agent-A") is None
