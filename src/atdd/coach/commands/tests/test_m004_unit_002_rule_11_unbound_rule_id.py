# URN: test:observe-and-correct:observer-runtime-and-rules:M004-UNIT-002-rule-11-unbound-rule-id
# Acceptance: acc:observe-and-correct:M004-UNIT-002-rule-11-unbound-rule-id
# WMBT: wmbt:observe-and-correct:M004
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M004-UNIT-002 — Rule ``coach.observer.unbound-rule-id-in-validator``
fires when an agent creates a validator that emits a Violation with a
rule_id but no ``bind_rule()`` call appears at module-import time
(SPEC-COACH-RULEID-0007). Correctly-bound validators do NOT fire.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_validator(content: str, tmp_path: Path, name: str = "test_x_validator.py") -> Path:
    """Author a fake validator file under <worktree>/src/atdd/<archetype>/validators/."""
    worktree = tmp_path / "worktree"
    target = worktree / "src" / "atdd" / "coder" / "validators" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return worktree


def _load_rule_11():
    from atdd.coach.commands import observer
    import atdd

    pkg_dir = Path(atdd.__file__).resolve().parent
    rule_path = pkg_dir / "coach" / "observer" / "rules" / "11-unbound-rule-id-in-validator.yaml"
    assert rule_path.exists()
    registry = observer.RuleRegistry()
    registry.load_dir(rule_path.parent)
    matches = [r for r in registry.rules if r.rule_id == "coach.observer.unbound-rule-id-in-validator"]
    assert matches, "rule 11 must load and bind"
    return matches[0]


def test_rule_11_fires_on_unbound_validator(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_validator(
        '''"""Validator missing bind_rule()."""
def test_thing():
    raise Violation(
        rule_id="coder.green.completion-without-commit",
        severity=4,
    )
''',
        tmp_path,
    )
    rule = _load_rule_11()
    rel = "src/atdd/coder/validators/test_x_validator.py"
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=(rel,),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is True


def test_rule_11_does_not_fire_when_bind_rule_present(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_validator(
        '''"""Validator with bind_rule() at module-import time."""
from atdd.coach.utils.rule_binding import bind_rule

_RULE = bind_rule("coder.green.completion-without-commit")

def test_thing():
    raise Violation(rule_id=_RULE.rule_id, severity=_RULE.severity)
''',
        tmp_path,
        name="test_y_validator.py",
    )
    rule = _load_rule_11()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/atdd/coder/validators/test_y_validator.py",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is False


def test_rule_11_correction_references_spec_and_rule_id(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_validator(
        '''"""Bad validator."""
def test_thing():
    raise Violation(rule_id="coder.green.completion-without-commit")
''',
        tmp_path,
        name="test_z_validator.py",
    )
    rule = _load_rule_11()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/atdd/coder/validators/test_z_validator.py",),
        worktree_root=worktree,
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None
    assert "SPEC-COACH-RULEID-0007" in correction.correction_text
    assert "coder.green.completion-without-commit" in correction.correction_text


def test_rule_11_skips_files_outside_validators(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = tmp_path / "worktree"
    src = worktree / "src" / "scripts" / "helper.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        '''def thing():
    raise Violation(rule_id="x.y.z")
''',
        encoding="utf-8",
    )
    rule = _load_rule_11()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/scripts/helper.py",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is False, (
        "non-validator paths are out of scope for rule 11"
    )
