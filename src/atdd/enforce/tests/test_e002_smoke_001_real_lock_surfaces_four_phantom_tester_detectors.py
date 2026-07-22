# URN: test:govern-providers:E002-SMOKE-001-real-lock-surfaces-the-four-phantom-tester-detectors
# Acceptance: acc:govern-providers:E002-SMOKE-001-real-lock-surfaces-the-four-phantom-tester-detectors
# WMBT: wmbt:govern-providers:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-providers:E002-SMOKE-001-real-lock-surfaces-the-four-phantom-tester-detectors.

Over the toolkit's own real committed ``.atdd/binding.lock.yaml`` and its vendored
``.atdd/extensions`` convention nodes, the orphan detector surfaces the four known
phantom ``tester.*`` bindings that no convention node declares — proving the
mechanism catches a real, live orphan set, not just a synthetic one.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.orphans import _convention_node_exists, find_orphan_detectors
from atdd.enforce.runner import resolve_substrate_home

_KNOWN_PHANTOM_ORPHANS = {
    "tester.acceptance-violation.live-smoke-acceptance-must-execute",
    "tester.acceptance-violation.metric-implementation-must-exist",
    "tester.smoke.no-collaborator-substitution",
    "tester.test-isolation.no-polluting-patterns",
}


def test_real_lock_surfaces_the_four_phantom_tester_detectors() -> None:
    substrate_home = resolve_substrate_home(find_repo_root())

    orphans = set(find_orphan_detectors(substrate_home))

    missing = _KNOWN_PHANTOM_ORPHANS - orphans
    assert not missing, f"orphan detector failed to surface known phantom bindings: {sorted(missing)}"

    # Each surfaced orphan genuinely has no convention node under .atdd/extensions.
    for orphan in _KNOWN_PHANTOM_ORPHANS:
        assert not _convention_node_exists(substrate_home, orphan)
