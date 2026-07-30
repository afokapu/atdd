# URN: test:verify-enforcement:E001-SMOKE-001-real-bound-twin-is-not-retirement-safe-under-advisory-path-b
# Acceptance: acc:verify-enforcement:E001-SMOKE-001-real-bound-twin-is-not-retirement-safe-under-advisory-path-b
# WMBT: wmbt:verify-enforcement:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:verify-enforcement:E001-SMOKE-001-real-bound-twin-is-not-retirement-safe-under-advisory-path-b.

Over the toolkit's real substrate and real CI, a core rule whose extension twin IS
bound is still NOT retirement-safe, because Path B is advisory. The succession
coverage the guard consumes is honest about the live enforcement hole.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.registry import path_b_is_blocking
from atdd.enforce.succession import (
    live_succession_coverage,
    retirement_precondition_holds,
)


def test_real_bound_twin_is_not_retirement_safe_under_advisory_path_b() -> None:
    repo = find_repo_root()

    # Path B (atdd enforce over the extensions) is NOT a blocking CI gate today.
    assert path_b_is_blocking(repo) is False

    coverage = live_succession_coverage(repo)
    assert coverage, "expected the real extension nodes to mirror core rules"

    # The real lock genuinely binds extension twins...
    bound_twins = [c for c in coverage if c.twin_bound]
    assert bound_twins, "expected at least one real core rule with a BOUND extension twin"

    # ...yet bound is not enough: Path B is advisory, so NONE of them is retirement-safe.
    assert all(not c.retirement_safe for c in bound_twins)

    # The precondition fails for a real bound-twinned core rule — retiring it would
    # silently drop its sole blocking enforcement.
    victim = bound_twins[0]
    assert retirement_precondition_holds(victim.rule_id, coverage) is False
