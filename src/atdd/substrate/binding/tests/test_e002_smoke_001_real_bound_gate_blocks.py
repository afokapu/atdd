# URN: test:bind-substrate-runtime:substrate-binding:E002-SMOKE-001-real-bound-gate-blocks
# Acceptance: acc:bind-substrate-runtime:E002-SMOKE-001-real-bound-gate-blocks
# WMBT: wmbt:bind-substrate-runtime:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E002-SMOKE-001 — a REAL provider-spawned implementation produces a Violation
that shadows the legacy validator and gates the transition end to end (real pytest
subprocess via the provider adapter, then the real router)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures"
_ADAPTER = _FIX / "provider" / "adapter"


@pytest.mark.smoke
def test_real_bound_violation_shadows_legacy_and_gates(tmp_path: Path) -> None:
    from atdd.substrate.binding import binder, router

    impl_path = tmp_path / "failing_impl"
    shutil.copytree(_FIX / "failing_impl", impl_path)

    # Real provider-spawn of a real failing implementation.
    spawn = binder.provider_spawn(
        adapter_dir=_ADAPTER,
        implementation_id="github.pr.merge-blocks-on-pre-smoke-close.impl",
        test_path=impl_path,
    )
    assert spawn.ran and spawn.violations  # the bound impl really detected a violation

    legacy_ran = {"hit": False}

    def run_legacy() -> list[dict]:
        legacy_ran["hit"] = True
        return [{"rule_id": "legacy", "location": ".", "evidence": "legacy"}]

    logs: list[str] = []
    outcome = router.route_convention(
        "github.pr.merge-blocks-on-pre-smoke-close",
        bound_spawn=spawn,
        run_legacy=run_legacy,
        log=logs.append,
    )

    # The bound Violation gates the transition; legacy is shadowed (not run), logged.
    assert outcome.source == router.SOURCE_BOUND
    assert outcome.violations  # transition would block
    assert outcome.shadowed_legacy is True
    assert legacy_ran["hit"] is False
    assert any("shadowed" in m for m in logs)
