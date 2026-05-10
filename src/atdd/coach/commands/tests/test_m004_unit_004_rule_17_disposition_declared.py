# URN: test:observe-and-correct:observer-runtime-and-rules:M004-UNIT-004-rule-17-disposition-declared
# Acceptance: acc:observe-and-correct:M004-UNIT-004-rule-17-disposition-declared
# WMBT: wmbt:observe-and-correct:M004
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M004-UNIT-004 — Rule ``coach.observer.repo-rule-disposition-declared``
fires when a diff adds a ``disposition:`` field to any acceptance or
abuse_case YAML. Correction surfaces the substrate v12 §4.4 contract.
Diffs without disposition declarations do NOT fire.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_yaml(file_relpath: str, body: str, tmp_path: Path) -> Path:
    worktree = tmp_path / "worktree"
    target = worktree / file_relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return worktree


def _load_rule_17():
    from atdd.coach.commands import observer
    import atdd

    pkg_dir = Path(atdd.__file__).resolve().parent
    rule_path = pkg_dir / "coach" / "observer" / "rules" / "17-repo-rule-disposition-declared.yaml"
    assert rule_path.exists()
    registry = observer.RuleRegistry()
    registry.load_dir(rule_path.parent)
    matches = [r for r in registry.rules if r.rule_id == "coach.observer.repo-rule-disposition-declared"]
    assert matches, "rule 17 must load and bind"
    return matches[0]


def test_rule_17_fires_on_acceptance_with_disposition(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_yaml(
        "plan/observe_and_correct/M999.yaml",
        """acceptances:
  - identity:
      urn: "acc:observe-and-correct:M999-UNIT-001-x"
    disposition: "advisory"
    harness:
      type: "unit"
""",
        tmp_path,
    )
    rule = _load_rule_17()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("plan/observe_and_correct/M999.yaml",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is True


def test_rule_17_fires_on_feature_abuse_case_with_disposition(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_yaml(
        "plan/observe_and_correct/features/x.yaml",
        """urn: "feature:observe-and-correct:x"
security:
  abuse_cases:
    - id: "abuse-1"
      threat: "thing"
      disposition: "strict"
""",
        tmp_path,
    )
    rule = _load_rule_17()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("plan/observe_and_correct/features/x.yaml",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is True


def test_rule_17_does_not_fire_when_disposition_absent(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_yaml(
        "plan/observe_and_correct/M888.yaml",
        """acceptances:
  - identity:
      urn: "acc:observe-and-correct:M888-UNIT-001-x"
    harness:
      type: "unit"
""",
        tmp_path,
    )
    rule = _load_rule_17()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("plan/observe_and_correct/M888.yaml",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is False


def test_rule_17_correction_text_states_substrate_contract(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_yaml(
        "plan/observe_and_correct/M777.yaml",
        """acceptances:
  - identity:
      urn: "acc:x:M777-UNIT-001-y"
    disposition: "strict"
""",
        tmp_path,
    )
    rule = _load_rule_17()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("plan/observe_and_correct/M777.yaml",),
        worktree_root=worktree,
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None
    text = correction.correction_text
    assert "Repo contract rules cannot declare disposition" in text
    assert "substrate v12 §4.4" in text
    assert "walker" in text


def test_rule_17_ignores_non_plan_yaml(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_yaml(
        "src/atdd/coder/conventions/x.convention.yaml",
        """rules:
  - id: "coder.green.x"
    disposition: "strict"
""",
        tmp_path,
    )
    rule = _load_rule_17()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/atdd/coder/conventions/x.convention.yaml",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is False, (
        "rule 17 only inspects plan/ trees (acceptance + feature YAML); "
        "convention rules legitimately declare disposition"
    )
