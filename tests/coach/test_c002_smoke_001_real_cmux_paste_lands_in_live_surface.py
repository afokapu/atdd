# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:C002-SMOKE-001-real-cmux-paste-lands-in-live-surface
# Acceptance: acc:spawn-agents:C002-SMOKE-001-real-cmux-paste-lands-in-live-surface
# WMBT: wmbt:spawn-agents:C002
# Phase: SMOKE
# Layer: assembly
# Smoke: true
# Purpose: A real guarded paste lands the prompt in the single live cmux surface, never in a stale/duplicate ref.
"""C002-SMOKE-001 — on a real cmux backend the guarded paste lands the prompt in
the single live surface and never in a forced stale/duplicate ref.

Live-on-demand: drives ``guarded_paste`` against real cmux surfaces. Skips cleanly
when not opted in (``ATDD_LIVE_SMOKE=1``) / when cmux is absent.

The hermetic C002 unit tier (test_c002_unit_001/002/003) carries the behavioural
guarantee. Live verification additionally requires the cmux surface-registry
adapter (live_surfaces_for/is_live/create_surface/reap_surface/paste over real
cmux) — pending per docs/smoke-audit.md (#1079 follow-up). Until then this records
the live entry point honestly rather than passing on a synthetic registry (the
#855 false-green anti-pattern).
"""
from __future__ import annotations

import os
import shutil

import pytest

pytestmark = [pytest.mark.smoke]


def test_real_cmux_paste_lands_in_live_surface():
    if os.environ.get("ATDD_LIVE_SMOKE") != "1":
        pytest.skip("live cmux smoke is opt-in: set ATDD_LIVE_SMOKE=1 (needs a live cmux backend)")
    if not shutil.which("cmux"):
        pytest.skip("cmux not on PATH")

    from atdd.coach.surface_guard import guarded_paste  # noqa: F401  (real entry point)

    pytest.skip(
        "pending wiring: a real cmux surface-registry adapter (backing "
        "live_surfaces_for/is_live/create_surface/reap_surface/paste over real "
        "cmux) is not yet implemented (docs/smoke-audit.md, #1079). The hermetic "
        "C002 unit tier carries the guarantee; this is NOT a synthetic-registry pass."
    )
