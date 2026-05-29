# URN: test:spawn-agents:E028-UNIT-003-process-alive-delay-probe-returns-after-min-delay
# Acceptance: acc:spawn-agents:E028-UNIT-003-process-alive-delay-probe-returns-after-min-delay
# WMBT: wmbt:spawn-agents:E028
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E028-UNIT-003 — ProcessAlivePlusDelayProbe.wait_for_ready returns after min_delay_s if proc alive

RED: fails with ImportError — ProcessAlivePlusDelayProbe does not exist until E022 GREEN phase.
"""
from __future__ import annotations

import time


class _AliveProc:
    """Fake proc whose poll() always returns None (alive throughout)."""

    def poll(self) -> None:
        return None


def test_process_alive_delay_probe_returns_after_min_delay():
    from atdd.coach.commands.spawn import ProcessAlivePlusDelayProbe  # ImportError until GREEN

    probe = ProcessAlivePlusDelayProbe(min_delay_s=0.05)

    t0 = time.monotonic()
    probe.wait_for_ready(
        surface_ref="surface:1",
        proc=_AliveProc(),
        timeout_s=2.0,
    )
    elapsed = time.monotonic() - t0

    assert elapsed >= 0.05, (
        f"ProcessAlivePlusDelayProbe did not enforce min_delay_s=0.05 — elapsed {elapsed:.3f}s"
    )
    assert elapsed < 1.0, (
        f"ProcessAlivePlusDelayProbe took unexpectedly long: {elapsed:.3f}s"
    )
