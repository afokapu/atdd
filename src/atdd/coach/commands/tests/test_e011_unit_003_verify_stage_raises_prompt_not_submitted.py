# URN: test:spawn-agents:coach-spawn-step-by-step-verify-each-stage:E011-UNIT-003-verify-stage-raises-prompt-not-submitted
# Acceptance: acc:spawn-agents:E011-UNIT-003-verify-stage-raises-prompt-not-submitted
# WMBT: wmbt:spawn-agents:E011
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E011-UNIT-003 — _verify_stage raises PromptNotSubmitted when capture_pane_text
never shows a thinking/tool-use indicator after Enter is sent.

RED: _verify_stage, PromptNotSubmitted do not exist yet (issue #799).
The swallowed-Enter failure mode means the input box retains the prompt
indefinitely — no thinking marker ever appears.
"""
from __future__ import annotations

import pytest


class _IdleAfterEnterMux:
    """capture_pane_text shows the prompt in the input box but no thinking marker.

    Simulates the swallowed-Enter case: the input text is visible but Claude
    never starts processing because Enter did not register.
    """

    def capture_pane_text(self, surface_ref: str) -> str:
        return "You are the planner agent for issue #799.\nPress Enter to send"


def test_verify_stage_raises_prompt_not_submitted_on_timeout():
    from atdd.coach.commands.spawn import (
        PromptNotSubmitted,
        _verify_stage,
    )

    mux = _IdleAfterEnterMux()
    with pytest.raises(PromptNotSubmitted):
        _verify_stage(
            stage_name="prompt-submitted",
            surface_ref="surface:3",
            backend=mux,
            expect_any=("⏺ Thinking", "⏺ Reading", "⏺ Bash", "⏺ Running", "⏺ Writing", "✶", "✻", "✳"),
            timeout_s=0.1,
            poll_interval_s=0.01,
        )


def test_verify_stage_passes_on_thinking_marker():
    from atdd.coach.commands.spawn import _verify_stage

    class _ThinkingMux:
        def capture_pane_text(self, surface_ref: str) -> str:
            return "⏺ Thinking... · ATDD42"

    _verify_stage(
        stage_name="prompt-submitted",
        surface_ref="surface:3",
        backend=_ThinkingMux(),
        expect_any=("⏺ Thinking", "⏺ Reading", "⏺ Bash", "⏺ Running", "⏺ Writing", "✶", "✻", "✳"),
        timeout_s=1.0,
        poll_interval_s=0.01,
    )


def test_verify_stage_passes_on_bash_marker():
    from atdd.coach.commands.spawn import _verify_stage

    class _BashMux:
        def capture_pane_text(self, surface_ref: str) -> str:
            return "⏺ Bash(gh issue view 799)"

    _verify_stage(
        stage_name="prompt-submitted",
        surface_ref="surface:3",
        backend=_BashMux(),
        expect_any=("⏺ Thinking", "⏺ Reading", "⏺ Bash", "⏺ Running", "⏺ Writing", "✶", "✻", "✳"),
        timeout_s=1.0,
        poll_interval_s=0.01,
    )


def test_prompt_not_submitted_is_a_worker_readiness_timeout():
    """PromptNotSubmitted should subclass WorkerReadinessTimeout for consistent handling."""
    from atdd.coach.commands.spawn import PromptNotSubmitted, WorkerReadinessTimeout

    assert issubclass(PromptNotSubmitted, WorkerReadinessTimeout)
