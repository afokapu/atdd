# URN: test:drive-state-machine:consolidate-store-writes:M002-UNIT-002-invariant-asserts-behavioral-exit-not-just-wiring
# Acceptance: acc:drive-state-machine:M002-UNIT-002-invariant-asserts-behavioral-exit-not-just-wiring
# WMBT: wmbt:drive-state-machine:M002
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: The #1220 state.single-store-per-control-root invariant asserts the observed non-zero-exit contract of the guard, not just that check_layout is defined and name-referenced.
"""RED Test for test:drive-state-machine:consolidate-store-writes:M002-UNIT-002.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:M002
Purpose: a guard that is defined + wired but TOOTHLESS (returns no violation on a
rogue layout) must fail the #1220 invariant. Today the invariant only greps for
the definition/wiring, so it would pass a toothless guard — this locks in a
behavioral probe.
"""
from __future__ import annotations

import atdd.state.paths as paths
from atdd.coder.validators.test_state_store_invariants import (
    scan_single_store_per_control_root,
)


def test_invariant_catches_a_toothless_guard(monkeypatch):
    # Neuter the guard: defined + still referenced by the CLI, but it reports NO
    # violation even on a rogue layout. A wiring-only invariant would miss this.
    monkeypatch.setattr(paths, "check_layout", lambda _root: [])

    violations = scan_single_store_per_control_root()

    assert violations, (
        "the #1220 invariant must exercise check_layout behaviorally and flag a "
        "toothless guard, not merely confirm it is defined and CLI-referenced"
    )
