# Acceptance: acc:govern-lifecycle:C002-UNIT-001-non-canonical-theme-is-flagged
# Acceptance: acc:govern-lifecycle:C002-SMOKE-001-plan-tree-has-no-non-canonical-theme
# Acceptance: acc:govern-lifecycle:E001-UNIT-001-schema-pattern-accepts-custom-themes
"""planner.theme.must-be-canonical validator (issue #970).

Enforces that every wagon ``theme:`` (and, by digit, every train theme) resolves
to one of the five canonical themes: commons/plan/test/code/coach (digits 0-4).
The retired game-domain names (digits 5-9) and any undeclared theme are rejected.

This subsumes the runtime theme-membership check described by
wmbt:govern-lifecycle:E001 (previously unbound — RULEID-0007 gap closed here).

Rule: planner.theme.must-be-canonical (severity 3)
Convention: src/atdd/planner/conventions/theme.convention.yaml::rules
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule

from ._theme_taxonomy import (
    CANONICAL_THEMES,
    RETIRED_THEMES,
    check_must_be_canonical,
    is_canonical_theme,
)

pytestmark = [pytest.mark.planner]

_RULE_ID = "planner.theme.must-be-canonical"
# NOTE: pass the literal id (not _RULE_ID) so the reverse rule-coherence
# scanner — which only recognizes ``bind_rule("<literal>")`` — binds this rule.
_RULE = bind_rule("planner.theme.must-be-canonical")

REPO_ROOT = find_repo_root()


def test_every_wagon_theme_is_canonical() -> None:
    """Repo-wide: no wagon declares a non-canonical theme."""
    violations = check_must_be_canonical(REPO_ROOT)
    assert violations == [], (
        f"[{_RULE_ID}] non-canonical wagon themes:\n"
        + "\n".join(f"  - {v.wagon}: theme={v.theme!r} ({v.path})" for v in violations)
    )


def test_retired_game_theme_is_flagged(tmp_path: Path) -> None:
    """A wagon declaring a retired game-domain theme is a violation."""
    wagon_dir = tmp_path / "plan" / "play_match"
    wagon_dir.mkdir(parents=True)
    (wagon_dir / "_play_match.yaml").write_text(
        "wagon: play-match\nurn: \"wagon:play-match\"\ntheme: match\n"
    )
    violations = check_must_be_canonical(tmp_path)
    assert any(v.theme == "match" for v in violations), (
        "expected the retired 'match' theme to be flagged"
    )


def test_canonical_themes_pass(tmp_path: Path) -> None:
    """Each of the five canonical themes validates clean."""
    for theme in CANONICAL_THEMES:
        wagon_dir = tmp_path / "plan" / f"w_{theme}"
        wagon_dir.mkdir(parents=True)
        (wagon_dir / f"_w_{theme}.yaml").write_text(
            f"wagon: w-{theme}\nurn: \"wagon:w-{theme}\"\ntheme: {theme}\n"
        )
    assert check_must_be_canonical(tmp_path) == []


def test_taxonomy_is_exactly_five() -> None:
    """Guard: the canonical set is the five themes and excludes game themes."""
    assert len(CANONICAL_THEMES) == 5
    assert is_canonical_theme("plan") and not is_canonical_theme("mechanic")
    assert set(CANONICAL_THEMES).isdisjoint(RETIRED_THEMES)
