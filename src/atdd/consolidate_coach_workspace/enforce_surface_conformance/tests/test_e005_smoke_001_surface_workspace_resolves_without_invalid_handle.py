# URN: test:consolidate-coach-workspace:enforce-surface-conformance:E005-SMOKE-001-surface-workspace-resolves-without-invalid-handle
# Acceptance: acc:consolidate-coach-workspace:E005-SMOKE-001-surface-workspace-resolves-without-invalid-handle
# WMBT: wmbt:consolidate-coach-workspace:E005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E005-SMOKE-001 — surface_workspace resolves live without Invalid handle (#1025).

Against a live cmux session with a real worker surface, surface_workspace must
return a bare ``workspace:N`` and never raise ``Invalid workspace handle`` — the
crash observed live on `atdd coach 1012`. Runs wherever cmux is on PATH; skips
otherwise (the coach exercises it live per docs/smoke-audit.md)."""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_e005_smoke_001_surface_workspace_resolves_without_invalid_handle():
    from atdd.consolidate_coach_workspace.enforce_surface_conformance.live_smoke import (
        surface_workspace_resolves_live_smoke,
    )

    evidence = surface_workspace_resolves_live_smoke()

    assert evidence["resolved_handle"].startswith("workspace:")
    assert "Invalid workspace handle" not in (evidence.get("error") or "")
