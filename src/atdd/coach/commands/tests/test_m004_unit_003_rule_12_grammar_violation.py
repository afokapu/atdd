# URN: test:observe-and-correct:observer-runtime-and-rules:M004-UNIT-003-rule-12-grammar-violation
# Acceptance: acc:observe-and-correct:M004-UNIT-003-rule-12-grammar-violation
# WMBT: wmbt:observe-and-correct:M004
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M004-UNIT-003 — Rule ``coach.observer.rule-id-grammar-violation``
fires when a rule declaration uses a non-canonical-grammar ``id`` per
SPEC-COACH-RULEID-0001. Correction directs the agent to canonical form
(``<archetype>.<convention>.<rule>``) and to place legacy IDs under
``aliases:``. Canonical-grammar IDs do NOT fire.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_convention(yaml_text: str, tmp_path: Path, name: str = "x.convention.yaml") -> Path:
    worktree = tmp_path / "worktree"
    target = worktree / "src" / "atdd" / "coder" / "conventions" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml_text, encoding="utf-8")
    return worktree


def _load_rule_12():
    from atdd.coach.commands import observer
    import atdd

    pkg_dir = Path(atdd.__file__).resolve().parent
    rule_path = pkg_dir / "coach" / "observer" / "rules" / "12-rule-id-grammar-violation.yaml"
    assert rule_path.exists()
    registry = observer.RuleRegistry()
    registry.load_dir(rule_path.parent)
    matches = [r for r in registry.rules if r.rule_id == "coach.observer.rule-id-grammar-violation"]
    assert matches, "rule 12 must load and bind"
    return matches[0]


def test_rule_12_fires_on_legacy_primary_id(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_convention(
        """version: "1.0"
rules:
  - id: "SPEC-COACH-RULEID-1234"
    severity: 3
    description: "legacy primary id"
""",
        tmp_path,
    )
    rule = _load_rule_12()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/atdd/coder/conventions/x.convention.yaml",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is True


def test_rule_12_does_not_fire_for_canonical_id(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_convention(
        """version: "1.0"
rules:
  - id: "coder.green.completion-without-commit"
    aliases: ["SPEC-COACH-RULEID-1234"]
    severity: 4
    description: "canonical id, legacy under aliases"
""",
        tmp_path,
        name="y.convention.yaml",
    )
    rule = _load_rule_12()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/atdd/coder/conventions/y.convention.yaml",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is False


def test_rule_12_correction_directs_to_canonical_and_aliases(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_convention(
        """rules:
  - id: "FREEFORM_THING"
    severity: 3
""",
        tmp_path,
        name="z.convention.yaml",
    )
    rule = _load_rule_12()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/atdd/coder/conventions/z.convention.yaml",),
        worktree_root=worktree,
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None
    text = correction.correction_text
    assert "<archetype>.<convention>.<rule>" in text
    assert "aliases" in text


def test_rule_12_ignores_non_convention_yaml(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = tmp_path / "worktree"
    target = worktree / "plan" / "x" / "M001.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """acceptances:
  - identity:
      id: "AC-UNIT-001"
""",
        encoding="utf-8",
    )
    rule = _load_rule_12()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("plan/x/M001.yaml",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is False
