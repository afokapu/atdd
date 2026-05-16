# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:D001-UNIT-001-distinct-name-per-persona
# Acceptance: acc:coach-wave-orchestration:D001-UNIT-001-distinct-name-per-persona
# WMBT: wmbt:coach-wave-orchestration:D001
# Phase: RED
# Layer: domain
# Runtime: python
# Assertion: behavioral
"""D001-UNIT-001 — ``compute_canonical_name`` yields distinct strings for two
personas/phases of the same issue.

RED: ``compute_canonical_name`` accepts ``repo, issue_number, slug, phase`` but
has no persona component, so two personas of the same issue resolve to one
identical name. This test pins a persona-qualified segment.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.session_naming import compute_canonical_name

pytestmark = [pytest.mark.platform]


def test_canonical_name_is_distinct_per_persona():
    """Planner and tester personas of one issue get distinct canonical names."""
    repo, issue, slug = "ATDD", 730, "coach-within-wave-serial-execution"

    planner_name = compute_canonical_name(repo, issue, slug, persona="planner")
    tester_name = compute_canonical_name(repo, issue, slug, persona="tester")

    # The two personas of the same issue must not collide.
    assert planner_name != tester_name, (
        f"planner and tester panes share an identical name: {planner_name!r}"
    )
    # Each name carries a persona/phase-qualified segment...
    assert "planner" in planner_name, (
        f"planner name {planner_name!r} carries no persona segment"
    )
    assert "tester" in tester_name, (
        f"tester name {tester_name!r} carries no persona segment"
    )
    # ...in addition to the issue number, which both still carry.
    assert str(issue) in planner_name
    assert str(issue) in tester_name
