# URN: test:bind-substrate-runtime:substrate-binding:E002-UNIT-001-shadow-and-gate
# Acceptance: acc:bind-substrate-runtime:E002-UNIT-001-shadow-and-gate
# WMBT: wmbt:bind-substrate-runtime:E002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E002-UNIT-001 — bound Violations for a convention shadow the legacy validator
(legacy suppressed + logged) and gate the transition; a convention with no bound
implementation is still gated by its legacy validator."""
from __future__ import annotations

from atdd.substrate.binding import router
from atdd.substrate.binding.binder import SpawnResult


def test_bound_shadows_legacy_and_gates() -> None:
    legacy_ran = {"x": False}

    def run_legacy_x() -> list[dict]:
        legacy_ran["x"] = True
        return [{"rule_id": "X", "location": ".", "evidence": "legacy"}]

    logs: list[str] = []
    spawn = SpawnResult(
        implementation_id="X.impl",
        ran=True,
        exit_code=1,
        violations=[{"rule_id": "X", "location": ".", "evidence": "bound-block"}],
    )

    outcome = router.route_convention(
        "X", bound_spawn=spawn, run_legacy=run_legacy_x, log=logs.append
    )

    # Convention X is gated by the bound Violation; the transition would block.
    assert outcome.source == router.SOURCE_BOUND
    assert outcome.violations == [{"rule_id": "X", "location": ".", "evidence": "bound-block"}]
    # The legacy validator for X was shadowed (not run) and the shadowing logged.
    assert outcome.shadowed_legacy is True
    assert legacy_ran["x"] is False
    assert any("shadowed" in m for m in logs)


def test_unbound_convention_uses_legacy() -> None:
    def run_legacy_y() -> list[dict]:
        return [{"rule_id": "Y", "location": ".", "evidence": "legacy-y"}]

    outcome = router.route_convention("Y", bound_spawn=None, run_legacy=run_legacy_y)

    assert outcome.source == router.SOURCE_LEGACY
    assert outcome.shadowed_legacy is False
    assert outcome.violations == [{"rule_id": "Y", "location": ".", "evidence": "legacy-y"}]
