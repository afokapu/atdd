# URN: test:govern-registry:E003-SMOKE-001-real-blocking-path-b-permits-real-core-succession
# Acceptance: acc:guard-succession:E003-SMOKE-001-real-blocking-path-b-permits-real-core-succession
# WMBT: wmbt:govern-registry:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:guard-succession:E003-SMOKE-001-real-blocking-path-b-permits-real-core-succession.

Over the toolkit's real CI wiring, Path B (``atdd enforce``) is now a BLOCKING gate
(#1428 E001), so succession for a bound-and-mirrored core rule is genuinely safe and
the guard permits deleting it.

This is the SAME guard, unchanged, reading a CHANGED WORLD. Its WMBT is untouched:
"refuse to delete any core convention node whose extension twin is not both bound AND
blockingly enforced in CI". When #1427 authored this SMOKE, Path B was the #1359
ADVISORY stage — the twin was bound but NOT blockingly enforced, so the guard refused,
recording a latent enforcement hole as live. #1428 closes that hole, so the live
evidence flips: the conjunct that was false is now true.

The guard must still BITE or this would be a hollow green, so the refusal is proven on
the arm that remains genuinely unsafe: an extension twin that is not bound at all.
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


def test_real_blocking_path_b_permits_real_core_succession() -> None:
    repo = find_repo_root()

    # Path B (atdd enforce) IS a blocking gate now — the enforce-extensions verdict
    # step carries neither `continue-on-error` nor `|| true` (#1428 E001).
    blocking = path_b_is_blocking(repo)
    assert blocking is True, (
        "Path B is not blocking — #1428 E001 has been reverted, and a bound twin's "
        "only blocking enforcement is Path A again"
    )

    # Pick a real core rule whose extension twin is bound in the real lock.
    bound = _bound_convention_ids(repo)
    twins = _twins_by_core_rule(repo)
    bound_and_mirrored = sorted(
        rid for rid, nodes in twins.items() if any(n.rule_id in bound for n in nodes)
    )
    assert bound_and_mirrored, "expected at least one bound-and-mirrored core rule"
    victim = bound_and_mirrored[0]

    # Twin bound AND Path B blocking -> enforcement survives the deletion -> permitted.
    assert guard_core_deletion([victim], repo, path_b_blocking=blocking) is None


def test_the_guard_still_refuses_an_unbound_twin_even_with_path_b_blocking() -> None:
    """The flip does not hollow the guard out: an UNBOUND twin is still refused.

    A blocking Path B only makes succession safe for a twin that is actually BOUND —
    a blocking gate that enforces nothing enforces nothing. Deleting a core rule whose
    extension twin is unbound would still silently strip its only enforcement.
    """
    repo = find_repo_root()

    bound = _bound_convention_ids(repo)
    twins = _twins_by_core_rule(repo)
    unbound_mirrored = sorted(
        rid
        for rid, nodes in twins.items()
        if nodes and not any(n.rule_id in bound for n in nodes)
    )
    if not unbound_mirrored:
        pytest.skip(
            "every mirrored core rule is bound in the real lock — no unbound twin to prove on"
        )

    victim = unbound_mirrored[0]
    with pytest.raises(CoreSuccessionError) as exc:
        guard_core_deletion([victim], repo, path_b_blocking=True)
    assert victim in str(exc.value)
