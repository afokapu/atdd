# URN: test:govern-registry:E003-SMOKE-001-real-advisory-path-b-blocks-real-core-deletion
# Acceptance: acc:govern-registry:E003-SMOKE-001-real-advisory-path-b-blocks-real-core-deletion
# WMBT: wmbt:govern-registry:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-registry:E003-SMOKE-001-real-advisory-path-b-blocks-real-core-deletion.

Over the toolkit's real CI wiring Path B is advisory, so deleting a real
bound-and-mirrored core rule is refused — proving the latent enforcement hole
exists live.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.registry import (
    CoreSuccessionError,
    _bound_convention_ids,
    _twins_by_core_rule,
    guard_core_deletion,
    path_b_is_blocking,
)


def test_real_advisory_path_b_blocks_real_core_deletion() -> None:
    repo = find_repo_root()

    # Path B (atdd enforce) is NOT a blocking gate today — the enforce-extensions
    # convention verdict is advisory / continue-on-error.
    blocking = path_b_is_blocking(repo)
    assert blocking is False

    # Pick a real core rule whose extension twin is bound in the real lock.
    bound = _bound_convention_ids(repo)
    twins = _twins_by_core_rule(repo)
    bound_and_mirrored = sorted(
        rid for rid, nodes in twins.items() if any(n.rule_id in bound for n in nodes)
    )
    assert bound_and_mirrored, "expected at least one bound-and-mirrored core rule"
    victim = bound_and_mirrored[0]

    # Its sole blocking enforcement is Path A; deleting it is refused.
    with pytest.raises(CoreSuccessionError) as exc:
        guard_core_deletion([victim], repo, path_b_blocking=blocking)
    assert victim in str(exc.value)
