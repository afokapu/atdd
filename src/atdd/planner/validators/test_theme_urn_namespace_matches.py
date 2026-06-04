# Acceptance: acc:govern-lifecycle:C004-UNIT-001-urn-prefix-mismatch-is-flagged
# Acceptance: acc:govern-lifecycle:C004-SMOKE-001-plan-tree-urn-prefixes-align
"""planner.theme.urn-namespace-matches validator (issue #970).

A wagon's produced contract/telemetry URN theme-prefix MUST equal the wagon's
declared ``theme:``. This catches artifacts like ``commons:decision:*`` living
under a wagon that should be (or becomes) ``coach``-themed, and is the tracking
mechanism for the commons:decision:* -> coach:decision:* migration deferred to
the #951 co-land.

Rule: planner.theme.urn-namespace-matches (severity 3)
Convention: src/atdd/planner/conventions/theme.convention.yaml::rules
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule

from ._theme_taxonomy import check_urn_namespace_matches, drop_deferred

pytestmark = [pytest.mark.planner]

_RULE_ID = "planner.theme.urn-namespace-matches"
_RULE = bind_rule(_RULE_ID)

REPO_ROOT = find_repo_root()


@pytest.mark.xfail(
    reason=(
        "Repo-wide URN re-namespacing is deferred to the #951 co-land: ~41 produced "
        "URNs (e.g. spawn-agents/dispatch-* producing coach:* while themed commons, "
        "plus commons:decision:* on mediate-worker-decisions) diverge from their "
        "current wagon theme. They are the re-theme worklist this slice intentionally "
        "does NOT migrate. Flips to xpass once #951 re-themes wagons + re-namespaces "
        "URNs. UNIT tests below prove the validator logic now."
    ),
    strict=False,
)
def test_produced_urn_prefix_matches_theme() -> None:
    """Repo-wide: produced URN theme-prefix == wagon theme (deferred to #951)."""
    violations = drop_deferred(check_urn_namespace_matches(REPO_ROOT))
    assert violations == [], (
        f"[{_RULE_ID}] URN theme-prefix mismatches:\n"
        + "\n".join(f"  - {v.wagon}: {v.detail} ({v.path})" for v in violations)
    )


def test_urn_prefix_mismatch_is_flagged(tmp_path: Path) -> None:
    """A coach wagon producing a commons:* URN is a violation."""
    wagon_dir = tmp_path / "plan" / "mediate_it"
    wagon_dir.mkdir(parents=True)
    (wagon_dir / "_mediate_it.yaml").write_text(
        "wagon: mediate-it\n"
        "urn: \"wagon:mediate-it\"\n"
        "theme: coach\n"
        "produce:\n"
        "  - name: commons:decision:record\n"
    )
    violations = check_urn_namespace_matches(tmp_path)
    assert any(v.wagon == "mediate-it" for v in violations)


def test_matching_prefix_passes(tmp_path: Path) -> None:
    """A coach wagon producing coach:* URNs validates clean."""
    wagon_dir = tmp_path / "plan" / "mediate_ok"
    wagon_dir.mkdir(parents=True)
    (wagon_dir / "_mediate_ok.yaml").write_text(
        "wagon: mediate-ok\n"
        "urn: \"wagon:mediate-ok\"\n"
        "theme: coach\n"
        "produce:\n"
        "  - name: coach:decision:record\n"
    )
    assert check_urn_namespace_matches(tmp_path) == []
