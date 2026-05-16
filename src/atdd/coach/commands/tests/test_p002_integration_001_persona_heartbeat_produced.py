# URN: test:observe-and-correct:observer-runtime-and-rules:P002-INTEGRATION-001-persona-heartbeat-produced
# Acceptance: acc:observe-and-correct:P002-INTEGRATION-001-persona-heartbeat-produced
# WMBT: wmbt:observe-and-correct:P002
# Phase: RED
# Layer: backend.integration
"""P002-INTEGRATION-001 — a heartbeat producer must run beside the persona.

Issue #713 scope item 2: ``heartbeat.json`` is writable via
``atdd agent heartbeat`` but nothing makes a running Claude persona emit
heartbeats on a timer, so rule 05 (missed-heartbeat) has no signal.

A heartbeat ticker must be co-spawned beside the persona; it refreshes
``runtime/agents/<persona-id>/heartbeat.json`` on the configured
interval while the persona is alive.

RED: fails today — no heartbeat producer (``start_heartbeat_ticker``)
exists in the observer module.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_heartbeat_ticker_refreshes_persona_heartbeat(tmp_path: Path):
    from atdd.coach.commands import observer

    persona_dir = tmp_path / ".atdd" / "runtime" / "agents" / "coder-713-h"
    persona_dir.mkdir(parents=True)

    start = getattr(observer, "start_heartbeat_ticker", None)
    assert start is not None, (
        "a heartbeat producer (start_heartbeat_ticker) must be co-spawned "
        "beside the persona so heartbeat.json is refreshed on a timer"
    )

    handle = start(agent_dir=persona_dir, interval=0.2)
    try:
        hb = persona_dir / "heartbeat.json"

        deadline = time.time() + 5.0
        while not hb.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert hb.exists(), "the heartbeat ticker must write heartbeat.json"

        first_mtime = hb.stat().st_mtime
        time.sleep(0.6)
        assert hb.stat().st_mtime > first_mtime, (
            "heartbeat.json mtime must advance on each heartbeat interval "
            "while the persona is alive"
        )
    finally:
        stop = getattr(handle, "stop", None)
        if callable(stop):
            stop()
