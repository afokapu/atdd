# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:M003-SMOKE-001-real-hung-warm-resume-times-out
# Acceptance: acc:spawn-agents:M003-SMOKE-001-real-hung-warm-resume-times-out
# WMBT: wmbt:spawn-agents:M003
# Phase: SMOKE
# Layer: assembly
# Smoke: true
# Purpose: A real hung coach warm-resume times out within budget and writes a structured escalation; no zombie spawn.
"""M003-SMOKE-001 — on real infrastructure a genuinely hung warm-resume times out
within the budget and writes an escalation (rescues the orchestrator from an
indefinite stall).

Live-on-demand: drives the REAL coach warm-resume branch under the watchdog.
Skips cleanly when not opted in (``ATDD_LIVE_SMOKE=1``).

The hermetic M003 unit tier (test_m003_unit_001/002/003) carries the behavioural
guarantee. Live verification additionally requires ``run_warm_resume_with_timeout``
to be wired around the issue_runner warm-resume branch (driving a real spawn that
hangs) — pending per docs/smoke-audit.md (#1079 follow-up). Until then this records
the live entry point honestly rather than passing on a ``sleep`` subprocess (the
#855 synthetic-fixture false-green anti-pattern).
"""
from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.smoke]


def test_real_hung_warm_resume_times_out():
    if os.environ.get("ATDD_LIVE_SMOKE") != "1":
        pytest.skip("live warm-resume smoke is opt-in: set ATDD_LIVE_SMOKE=1 (needs a live coach warm-resume)")

    from atdd.train.warm_resume_watchdog import run_warm_resume_with_timeout  # noqa: F401

    pytest.skip(
        "pending wiring: run_warm_resume_with_timeout is not yet wrapped around "
        "the issue_runner warm-resume branch driving a real hung spawn "
        "(docs/smoke-audit.md, #1079). The hermetic M003 unit tier carries the "
        "guarantee; this is NOT a synthetic sleep-subprocess pass."
    )
