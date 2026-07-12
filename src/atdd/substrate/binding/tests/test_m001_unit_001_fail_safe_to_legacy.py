# URN: test:bind-substrate-runtime:substrate-binding:M001-UNIT-001-fail-safe-to-legacy
# Acceptance: acc:bind-substrate-runtime:M001-UNIT-001-fail-safe-to-legacy
# WMBT: wmbt:bind-substrate-runtime:M001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""M001-UNIT-001 — a bound implementation that crashes, times out, or emits
malformed output falls back to the legacy validator for its convention and
surfaces a loud error; it never passes the gate by default (never fail-open)."""
from __future__ import annotations

import pytest

from atdd.substrate.binding import router
from atdd.substrate.binding.binder import SpawnResult

# The three ways a provider-spawn fails to produce a usable result — each yields
# SpawnResult.ran == False (the M001 signal).
FAILURE_MODES = [
    SpawnResult("X.impl", ran=False, exit_code=2, error="provider-spawn produced no parseable result line"),
    SpawnResult("X.impl", ran=False, exit_code=-1, error="provider-spawn timed out after 300s"),
    SpawnResult("X.impl", ran=False, exit_code=0, error="provider-spawn produced no parseable result line"),
]


@pytest.mark.parametrize("spawn", FAILURE_MODES, ids=["crash", "timeout", "malformed"])
def test_failed_bind_falls_back_to_legacy_loudly(spawn: SpawnResult) -> None:
    legacy_ran = {"x": False}

    def run_legacy_x() -> list[dict]:
        legacy_ran["x"] = True
        return [{"rule_id": "X", "location": ".", "evidence": "legacy"}]

    logs: list[str] = []
    outcome = router.route_convention(
        "X", bound_spawn=spawn, run_legacy=run_legacy_x, log=logs.append
    )

    # Fail-safe: the legacy validator ran and gates the convention.
    assert outcome.source == router.SOURCE_LEGACY_FALLBACK
    assert legacy_ran["x"] is True
    assert outcome.violations == [{"rule_id": "X", "location": ".", "evidence": "legacy"}]

    # A loud, attributable error was logged.
    assert any("[ERROR]" in m and "falling back to legacy" in m for m in logs)

    # Never fail-open: the failed bound impl did not silently pass the gate as
    # a clean "bound" source with no violations.
    assert outcome.source != router.SOURCE_BOUND
