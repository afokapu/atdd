# URN: test:observe-and-correct:observer-runtime-and-rules:M004-UNIT-001-rule-10-stale-suppression
# Acceptance: acc:observe-and-correct:M004-UNIT-001-rule-10-stale-suppression
# WMBT: wmbt:observe-and-correct:M004
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M004-UNIT-001 — Rule ``coach.observer.stale-suppression-detected``
fires when a commit touches a file containing
``# atdd:suppress(<toolkit-rule-id>) [UNTIL=<past>]``, uses the existing
``find_stale_suppressions``, and DOES NOT fire for ``repo.*`` rule IDs
(unsuppressible per substrate v12 §2) nor for non-stale markers.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_worktree_with(file_relpath: str, content: str, tmp_path: Path) -> Path:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    target = worktree / file_relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return worktree


def _load_rule_10():
    """Helper — load the substrate-aware stale-suppression rule via the
    registry from the toolkit-shipped rules dir."""
    from atdd.coach.commands import observer
    import atdd

    pkg_dir = Path(atdd.__file__).resolve().parent
    rule_path = pkg_dir / "coach" / "observer" / "rules" / "10-stale-suppression-detected.yaml"
    assert rule_path.exists(), (
        f"rule 10 YAML must ship under the toolkit at {rule_path}"
    )
    registry = observer.RuleRegistry()
    registry.load_dir(rule_path.parent)
    matches = [r for r in registry.rules if r.rule_id == "coach.observer.stale-suppression-detected"]
    assert matches, "rule 10 must load and bind to coach.observer.stale-suppression-detected"
    return matches[0]


def test_rule_10_fires_on_stale_toolkit_marker(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_worktree_with(
        "src/foo.py",
        "x = 1  # atdd:suppress(coder.green.completion-without-commit) UNTIL=2025-01-01\n",
        tmp_path,
    )

    rule = _load_rule_10()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/foo.py",),
        worktree_root=worktree,
    )
    fired = rule.predicate(ctx)
    assert fired is True, "stale toolkit suppression must fire rule 10"


def test_rule_10_does_not_fire_for_repo_rule_id(tmp_path: Path):
    """Substrate v12 §2: repo rules are unsuppressible. A `repo.*` stale
    marker must not fire rule 10 — the substrate validator catches the
    underlying violation; firing here would direct the operator to "fix" a
    marker that was never effective."""
    from atdd.coach.commands import observer

    worktree = _make_worktree_with(
        "src/bar.py",
        "x = 1  # atdd:suppress(repo.observe-and-correct.M004-acc-unit-001) UNTIL=2025-01-01\n",
        tmp_path,
    )
    rule = _load_rule_10()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/bar.py",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is False, (
        "rule 10 must NOT fire for repo.* stale markers (substrate v12 §2)"
    )


def test_rule_10_does_not_fire_for_future_until(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_worktree_with(
        "src/baz.py",
        "x = 1  # atdd:suppress(coder.green.completion-without-commit) UNTIL=2099-12-31\n",
        tmp_path,
    )
    rule = _load_rule_10()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/baz.py",),
        worktree_root=worktree,
    )
    assert rule.predicate(ctx) is False, "non-stale markers (UNTIL future) must not fire"


def test_rule_10_correction_text_names_rule_id_and_location(tmp_path: Path):
    from atdd.coach.commands import observer

    worktree = _make_worktree_with(
        "src/foo.py",
        "x = 1  # atdd:suppress(coder.green.completion-without-commit) UNTIL=2025-01-01\n",
        tmp_path,
    )
    rule = _load_rule_10()
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        worktree_changes=("src/foo.py",),
        worktree_root=worktree,
    )
    correction = rule.evaluate(ctx, agent_id="agent-A")
    assert correction is not None
    text = correction.correction_text
    assert "Stale suppression marker" in text
    assert "expired" in text or "UNTIL" in text
