# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:C002-SMOKE-001-real-cmux-paste-lands-in-live-surface
# Acceptance: acc:spawn-agents:C002-SMOKE-001-real-cmux-paste-lands-in-live-surface
# WMBT: wmbt:spawn-agents:C002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C002-SMOKE-001 — on a real cmux backend the guarded paste lands the prompt in
the single live surface and never in a forced stale/duplicate ref.

Live-on-demand against real cmux. Skips in CI / when not opted in
(ATDD_RUN_SMOKE=1). In RED the live-smoke harness is unimplemented → skipped.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("ATDD_RUN_SMOKE") != "1",
        reason="live cmux single-live-surface smoke — opt in with ATDD_RUN_SMOKE=1",
    ),
]


def test_real_cmux_paste_lands_in_live_surface():
    from atdd.coach.surface_guard.live_smoke import (  # noqa: WPS433
        paste_lands_in_live_surface_live_smoke,
    )

    evidence = paste_lands_in_live_surface_live_smoke()

    assert evidence["prompt_in_live_surface"] is True, "prompt observed in the live surface"
    assert evidence["pasted_into_stale"] is False, "nothing pasted into the stale/duplicate ref"
    assert evidence["live_surface_count"] == 1, "exactly one live surface remains for the issue"
