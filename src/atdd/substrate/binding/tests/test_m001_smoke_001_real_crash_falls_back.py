# URN: test:bind-substrate-runtime:substrate-binding:M001-SMOKE-001-real-crash-falls-back
# Acceptance: acc:bind-substrate-runtime:M001-SMOKE-001-real-crash-falls-back
# WMBT: wmbt:bind-substrate-runtime:M001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""M001-SMOKE-001 — a REAL bound implementation that crashes under provider-spawn
(pytest collection error) falls back to the legacy validator and logs loudly; the
gate is never silently passed (real pytest subprocess via the provider adapter)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures"
_ADAPTER = _FIX / "provider" / "adapter"


@pytest.mark.smoke
def test_real_crash_falls_back_to_legacy_loudly(tmp_path: Path) -> None:
    from atdd.substrate.binding import binder, router

    impl_path = tmp_path / "crashing_impl"
    shutil.copytree(_FIX / "crashing_impl", impl_path)

    # Real provider-spawn of an implementation that crashes at collection.
    spawn = binder.provider_spawn(
        adapter_dir=_ADAPTER,
        implementation_id="broken.impl",
        test_path=impl_path,
    )
    # The provider could not produce a clean pass/fail result.
    assert spawn.ran is False

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

    # Fail-safe: legacy ran and gates; never a silent clean pass.
    assert outcome.source == router.SOURCE_LEGACY_FALLBACK
    assert legacy_ran["hit"] is True
    assert outcome.source != router.SOURCE_BOUND
    assert any("[ERROR]" in m and "falling back to legacy" in m for m in logs)
