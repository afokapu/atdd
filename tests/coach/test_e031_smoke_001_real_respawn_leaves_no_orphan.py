# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:E031-SMOKE-001-real-respawn-leaves-no-orphan
# Acceptance: acc:spawn-agents:E031-SMOKE-001-real-respawn-leaves-no-orphan
# WMBT: wmbt:spawn-agents:E031
# Phase: SMOKE
# Layer: assembly
# Smoke: true
# Purpose: A real coach respawn reaps the prior worker process, leaving exactly one fresh process and no orphan.
"""E031-SMOKE-001 — on real infrastructure the kill-before-respawn path removes
the prior worker process, leaving exactly one fresh process and no orphan/ghost.

Live-on-demand: drives the REAL coach phase-transition respawn against a live
multiplexer backend + real worker process. Skips cleanly when not opted in
(``ATDD_LIVE_SMOKE=1``) so ordinary/CI runs never spawn a real worker.

The hermetic E031 unit tier (test_e031_unit_001/002/003) carries the behavioural
guarantee. Live verification additionally requires ``respawn_worker`` to be wired
into the coach transition path and ``AgentController.is_alive`` to exist on the
real controllers — pending per docs/smoke-audit.md (#1079 follow-up). Until then
this records the live entry point honestly rather than passing on synthetic
process fixtures (the #855 false-green anti-pattern).
"""
from __future__ import annotations

import os
import shutil

import pytest

pytestmark = [pytest.mark.smoke]


def test_real_respawn_leaves_no_orphan():
    if os.environ.get("ATDD_LIVE_SMOKE") != "1":
        pytest.skip("live respawn smoke is opt-in: set ATDD_LIVE_SMOKE=1 (needs a live multiplexer + worker)")
    if not shutil.which("cmux"):
        pytest.skip("cmux not on PATH")

    from atdd.coach.respawn_guards import respawn_worker  # noqa: F401  (real entry point)

    pytest.skip(
        "pending wiring: respawn_worker is not yet invoked on the live coach "
        "transition path and AgentController.is_alive is not implemented on the "
        "real controllers (docs/smoke-audit.md, #1079). The hermetic E031 unit "
        "tier carries the guarantee; this is NOT a synthetic-fixture pass."
    )
