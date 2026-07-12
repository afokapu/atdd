# URN: test:govern-lifecycle:smoke-false-green-prevention:L002-SMOKE-001-meta-walker-zero-hits-on-post-retrofit-repo
# Acceptance: acc:govern-lifecycle:L002-SMOKE-001-meta-walker-zero-hits-on-post-retrofit-repo
# WMBT: wmbt:govern-lifecycle:L002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""
SMOKE: walk_all_smoke_acceptances_for_anti_patterns must return zero hits when
run against the live post-retrofit repo.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.planner.validators._meta_walker import (
    walk_all_smoke_acceptances_for_anti_patterns,
)

pytestmark = [pytest.mark.smoke, pytest.mark.platform]


def test_meta_walker_zero_hits_on_post_retrofit_repo():
    """Meta-walker returns empty list on the live repo after all E029 retrofits are committed."""
    repo_root = find_repo_root()
    plan_dir = repo_root / "plan"
    hits = walk_all_smoke_acceptances_for_anti_patterns(plan_dir)
    assert not hits, (
        f"Meta-walker found {len(hits)} synthetic-fixture anti-pattern(s) in the "
        "post-retrofit repo — all SMOKE tests must drive real entry points:\n"
        + "\n".join(f"  {urn}: {desc[:120]}" for urn, desc in hits)
        + "\n\nFix: retrofit the identified SMOKE tests or add an inline suppression "
        "with a tracked follow-up."
    )
