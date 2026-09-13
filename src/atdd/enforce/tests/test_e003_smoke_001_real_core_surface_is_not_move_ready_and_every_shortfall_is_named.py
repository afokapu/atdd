# URN: test:govern-registry:E003-SMOKE-001-real-core-surface-is-not-move-ready-and-every-shortfall-is-named
# Acceptance: acc:govern-registry:E003-SMOKE-001-real-core-surface-is-not-move-ready-and-every-shortfall-is-named
# WMBT: wmbt:govern-registry:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-registry:E003-SMOKE-001-real-core-surface-is-not-move-ready-and-every-shortfall-is-named.

Over the toolkit's real substrate — its real ``src/atdd/{coder,tester}/conventions``
trees, its real vendored ``.atdd/extensions`` nodes, and its committed classification
record — the measure reports the actual core surface, refuses to certify it move-ready,
and names every uncovered rule. That verdict is what a carve-out consumes instead of
re-measuring for itself (#1993 declares the coverage work out of its scope).

No count is asserted. The shortfall falls as families land, and a test pinned to
today's number would fail on progress; what must hold at every size is that the
partition is exact and carries no false positive in either direction.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.twin_coverage import (
    CLASSIFICATION_RECORD,
    live_twin_coverage,
    twins_by_core_rule,
    why_not_verdicts,
)

# One rule declared in a nested monolith list, one in an atomized node: the measured
# surface must be the whole declaration set, not whichever half a reader can see.
_NESTED_IN_A_MONOLITH = "coder.logging.print"
_ATOMIZED_NODE = "coder.state-store.core-imports-no-providers"


def test_real_core_surface_is_not_move_ready_and_every_shortfall_is_named() -> None:
    repo = find_repo_root()
    coverage = live_twin_coverage(repo)

    # The measured surface is the whole coder/tester declaration set.
    assert coverage.core_surface, "no core coder/tester rules measured"
    assert _NESTED_IN_A_MONOLITH in coverage.core_surface, (
        "a rule declared under canonical_rules.rules[] is missing from the measured "
        "surface — the walker has regressed to a depth-1 read"
    )
    assert _ATOMIZED_NODE in coverage.core_surface

    # It is NOT move-ready: at least one core rule is neither mirrored nor classified.
    assert coverage.move_ready is False
    assert coverage.uncovered, "not move-ready, yet no rule is named as the shortfall"

    twins = twins_by_core_rule(repo)
    why_not = why_not_verdicts(repo / CLASSIFICATION_RECORD)

    # No false positive: every rule named uncovered is genuinely absent from both
    # surfaces. A shortfall that over-reports is worse than none — it sends a worker
    # to author a node for an obligation that already exists.
    for rule_id in coverage.uncovered:
        assert rule_id not in twins, (
            f"{rule_id} is reported uncovered but an extension node mirrors it: "
            f"{twins.get(rule_id)}"
        )
        assert rule_id not in why_not, (
            f"{rule_id} is reported uncovered but the classification record carries "
            "a why-not verdict for it"
        )

    # And no false negative in the other direction: a rule already carved out is not
    # re-reported as work.
    for rule_id in twins:
        if rule_id in coverage.core_surface:
            assert rule_id not in coverage.uncovered

    # The record's verdicts are about real core rules, not stale ids — otherwise a
    # rule could be "covered" by a verdict naming something that no longer exists.
    for rule_id in why_not:
        assert rule_id in coverage.core_surface, (
            f"the classification record carries a verdict for {rule_id}, which is not "
            "a live core coder/tester rule"
        )
