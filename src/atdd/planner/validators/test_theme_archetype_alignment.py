# Acceptance: acc:govern-lifecycle:C005-UNIT-001-misaligned-archetype-theme-is-flagged
# Acceptance: acc:govern-lifecycle:C005-UNIT-002-scanner-surfaces-existing-themes
# Acceptance: acc:govern-lifecycle:C005-SMOKE-001-plan-tree-archetype-themes-align
# Acceptance: acc:govern-lifecycle:L001-UNIT-001-scanner-surfaces-existing-themes
"""planner.theme.archetype-alignment validator (issue #970).

The plan/test/code themes align to the planner/tester/coder archetypes. A wagon
themed ``code`` whose implementation lives outside a coder-archetype source root
(or ``plan`` outside planner, ``test`` outside tester) is surfaced.

This validator also exercises the theme-discovery scan across plan/ described by
wmbt:govern-lifecycle:L001 (previously unbound — RULEID-0007 gap closed here).

Rule: planner.theme.archetype-alignment (severity 2, documentation-only)
Convention: src/atdd/planner/conventions/theme.convention.yaml::rules
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule

from ._theme_taxonomy import (
    ARCHETYPE_THEME_ROOTS,
    check_archetype_alignment,
    scan_wagon_themes,
)

pytestmark = [pytest.mark.planner]

_RULE_ID = "planner.theme.archetype-alignment"
_RULE = bind_rule(_RULE_ID)

REPO_ROOT = find_repo_root()


def test_archetype_themes_align_with_source_roots() -> None:
    """Repo-wide: plan/test/code wagons live under their archetype root."""
    violations = check_archetype_alignment(REPO_ROOT)
    assert violations == [], (
        f"[{_RULE_ID}] archetype/theme misalignments:\n"
        + "\n".join(f"  - {v.wagon}: theme={v.theme!r} {v.detail}" for v in violations)
    )


def test_scanner_surfaces_existing_themes() -> None:
    """L001: the theme scanner returns distinct themes declared under plan/."""
    found = scan_wagon_themes(REPO_ROOT)
    themes = {theme for theme, _path in found.values()}
    # Today every wagon is `commons`; the scan must at least surface that.
    assert themes, "scan_wagon_themes returned no themes from plan/"


def test_aligned_archetype_theme_passes(tmp_path: Path) -> None:
    """A `code` wagon under a coder root validates clean."""
    assert "code" in ARCHETYPE_THEME_ROOTS
    wagon_dir = tmp_path / "plan" / "impl_thing"
    wagon_dir.mkdir(parents=True)
    (wagon_dir / "_impl_thing.yaml").write_text(
        "wagon: impl-thing\nurn: \"wagon:impl-thing\"\ntheme: code\n"
    )
    src = tmp_path / "src" / "atdd" / "coder" / "impl_thing"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    assert check_archetype_alignment(tmp_path) == []
