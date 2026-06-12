# URN: test:mediate-worker-decisions:verify-producer-gate:M006-SMOKE-001-live-gate-asserts-daemon-attached-before-handled
# Acceptance: acc:mediate-worker-decisions:M006-SMOKE-001-live-gate-asserts-daemon-attached-before-handled
# WMBT: wmbt:mediate-worker-decisions:M006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""M006-SMOKE-001 — the live gate asserts a daemon attach before HANDLED.

Live end-to-end against a real spawned worker that publishes a gated decision: with a
daemon attached to the worker's workspace the gate confirms the attach and records the
decision HANDLED; with no daemon attached the gate flags the worker unmediated rather
than silently HANDLED (the #1084/A1 false-success). Skips cleanly in CI / when not
opted in (ATDD_LIVE_SMOKE=1).
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.verify_producer_gate.live_smoke import (
    live_smoke_available,
    mediation_attach_gate_live_smoke,
)


def test_m006_smoke_001_live_gate_asserts_daemon_attached_before_handled():
    skip = live_smoke_available()
    if skip:
        pytest.skip(skip)
    evidence = mediation_attach_gate_live_smoke()
    # A confirmed attach yields HANDLED for the published decision.
    assert evidence["handled_when_attached"] is True
    # No attached daemon: flagged unmediated, NOT silently recorded HANDLED.
    assert evidence["handled_when_unattached"] is False
