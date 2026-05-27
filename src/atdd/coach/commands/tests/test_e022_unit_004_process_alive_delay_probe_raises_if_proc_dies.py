# URN: test:spawn-agents:E022-UNIT-004-process-alive-delay-probe-raises-if-proc-dies
# Acceptance: acc:spawn-agents:E022-UNIT-004-process-alive-delay-probe-raises-if-proc-dies
# WMBT: wmbt:spawn-agents:E022
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E022-UNIT-004 — ProcessAlivePlusDelayProbe.wait_for_ready raises WorkerReadinessTimeout if proc dies

RED: fails with ImportError — ProcessAlivePlusDelayProbe does not exist until E022 GREEN phase.
"""
from __future__ import annotations

import pytest


class _DeadProc:
    """Fake proc whose poll() immediately returns 1 (process exited on start)."""

    def poll(self) -> int:
        return 1


def test_process_alive_delay_probe_raises_if_proc_dies():
    from atdd.coach.commands.spawn import (  # ImportError until GREEN
        ProcessAlivePlusDelayProbe,
        WorkerReadinessTimeout,
    )

    probe = ProcessAlivePlusDelayProbe(min_delay_s=5.0)

    with pytest.raises(WorkerReadinessTimeout) as exc_info:
        probe.wait_for_ready(
            surface_ref="surface:1",
            proc=_DeadProc(),
            timeout_s=2.0,
        )

    msg = str(exc_info.value)
    assert "surface:1" in msg, (
        f"WorkerReadinessTimeout message should contain the surface_ref. Got: {msg!r}"
    )
