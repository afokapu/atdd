# Acceptance: acc:govern-lifecycle:C003-UNIT-001-commons-wagon-importing-coach-is-flagged
# Acceptance: acc:govern-lifecycle:C003-SMOKE-001-plan-tree-respects-boundary
"""planner.theme.commons-coach-boundary validator (issue #970).

The one sharp line: a wagon is ``commons`` IFF a non-coach archetype can consume
its artifacts without importing ``atdd.coach``. Concretely, no module under a
``commons``-themed wagon's source tree may ``import atdd.coach``. Coach-only
machinery (multiplexer/pane spawn, durable run persistence, the Feed daemon,
worker-decision mediation) must declare ``theme: coach``.

Known deferred violation: mediate-worker-decisions is themed ``commons`` but its
src imports coach. It is suppressed UNTIL the #951 co-land re-themes it to
``coach`` and re-namespaces commons:decision:* -> coach:decision:*.

Rule: planner.theme.commons-coach-boundary (severity 3)
Convention: src/atdd/planner/conventions/theme.convention.yaml::rules
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule

from ._theme_taxonomy import check_commons_coach_boundary, drop_deferred

pytestmark = [pytest.mark.planner]

_RULE_ID = "planner.theme.commons-coach-boundary"
# Literal id so the reverse rule-coherence scanner binds this rule.
_RULE = bind_rule("planner.theme.commons-coach-boundary")

REPO_ROOT = find_repo_root()


def test_commons_wagons_do_not_import_coach() -> None:
    """Repo-wide: no commons wagon imports atdd.coach (minus #951 carve-out)."""
    violations = drop_deferred(check_commons_coach_boundary(REPO_ROOT))
    assert violations == [], (
        f"[{_RULE_ID}] commons wagons importing atdd.coach:\n"
        + "\n".join(f"  - {v.wagon}: {v.detail} ({v.path})" for v in violations)
    )


def test_commons_wagon_importing_coach_is_flagged(tmp_path: Path) -> None:
    """A commons wagon whose src imports atdd.coach is a violation."""
    wagon_dir = tmp_path / "plan" / "do_thing"
    wagon_dir.mkdir(parents=True)
    (wagon_dir / "_do_thing.yaml").write_text(
        "wagon: do-thing\nurn: \"wagon:do-thing\"\ntheme: commons\n"
    )
    src = tmp_path / "src" / "atdd" / "do_thing"
    src.mkdir(parents=True)
    (src / "runner.py").write_text("from atdd.coach.commands import coach\n")
    violations = check_commons_coach_boundary(tmp_path)
    assert any(v.wagon == "do-thing" for v in violations)


def test_coach_themed_wagon_may_import_coach(tmp_path: Path) -> None:
    """A coach-themed wagon importing atdd.coach is fine."""
    wagon_dir = tmp_path / "plan" / "drive_it"
    wagon_dir.mkdir(parents=True)
    (wagon_dir / "_drive_it.yaml").write_text(
        "wagon: drive-it\nurn: \"wagon:drive-it\"\ntheme: coach\n"
    )
    src = tmp_path / "src" / "atdd" / "drive_it"
    src.mkdir(parents=True)
    (src / "runner.py").write_text("import atdd.coach\n")
    assert check_commons_coach_boundary(tmp_path) == []
