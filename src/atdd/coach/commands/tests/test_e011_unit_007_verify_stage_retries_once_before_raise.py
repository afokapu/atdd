# URN: test:spawn-agents:coach-spawn-step-by-step-verify-each-stage:E011-UNIT-007-verify-stage-retries-once-before-raise
# Acceptance: acc:spawn-agents:E011-UNIT-007-verify-stage-retries-once-before-raise
# WMBT: wmbt:spawn-agents:E011
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E011-UNIT-007 — _verify_stage includes stage name in the exception message so
callers can log which exact stage failed.

RED: _verify_stage does not exist yet (issue #799).
"""
from __future__ import annotations

import pytest


class _NeverSucceedsMux:
    def capture_pane_text(self, surface_ref: str) -> str:
        return "Press Enter to send"


def test_verify_stage_exception_includes_stage_name():
    from atdd.coach.commands.spawn import WorkerReadinessTimeout, _verify_stage

    mux = _NeverSucceedsMux()
    with pytest.raises(WorkerReadinessTimeout) as exc_info:
        _verify_stage(
            stage_name="paste-landed",
            surface_ref="surface:9",
            backend=mux,
            expect_any=("paste again to expand",),
            timeout_s=0.1,
            poll_interval_s=0.01,
        )
    assert "paste-landed" in str(exc_info.value)


def test_verify_stage_exception_includes_surface_ref():
    from atdd.coach.commands.spawn import WorkerReadinessTimeout, _verify_stage

    mux = _NeverSucceedsMux()
    with pytest.raises(WorkerReadinessTimeout) as exc_info:
        _verify_stage(
            stage_name="rename-accepted",
            surface_ref="surface:42",
            backend=mux,
            expect_any=("ATDD99",),
            timeout_s=0.1,
            poll_interval_s=0.01,
        )
    assert "surface:42" in str(exc_info.value)


def test_verify_stage_succeeds_on_second_poll():
    """_verify_stage succeeds when the signal appears on the second capture call."""
    from atdd.coach.commands.spawn import _verify_stage

    call_count = 0

    class _SecondPollMux:
        def capture_pane_text(self, surface_ref: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "Press Enter to send"
            return "⏺ Thinking..."

    _verify_stage(
        stage_name="prompt-submitted",
        surface_ref="surface:3",
        backend=_SecondPollMux(),
        expect_any=("⏺ Thinking",),
        timeout_s=2.0,
        poll_interval_s=0.01,
    )
    assert call_count >= 2
