"""Live cmux orchestration for the enforce-surface-conformance SMOKE acceptances.

Kept out of the test files (per the bridge-cmux-feed live-smoke pattern) so the
tests stay thin and skip cleanly when cmux is absent. These drive REAL cmux:
create per-workspace surfaces, run the real conformance pass, and read back
``surface.list`` per workspace.

RED stubs raise NotImplementedError; implemented in the SMOKE phase.
"""
from __future__ import annotations

from typing import Any


def never_collapse_live_smoke(*, evidence_path: str, worker_count: int = 2) -> dict[str, Any]:
    """Spawn ``worker_count`` real per-workspace surfaces, run the conformance
    layout pass, and return evidence proving each worker still resolves to its own
    single-identity workspace (surface.list per workspace yields exactly one
    identity; no shared workspace)."""
    raise NotImplementedError(
        "enforce-surface-conformance: never_collapse_live_smoke (SMOKE phase)"
    )


def naming_validator_live_smoke(*, evidence_path: str) -> dict[str, Any]:
    """Run the bound role-aware naming validator over a real cmux ``surface.list``;
    return evidence that a role-aware managed name passes and a drifted name is
    flagged."""
    raise NotImplementedError(
        "enforce-surface-conformance: naming_validator_live_smoke (SMOKE phase)"
    )
