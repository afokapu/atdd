# URN: test:spawn-agents:coach-spawn-step-by-step-verify-each-stage:E011-UNIT-002-verify-stage-raises-paste-did-not-land
# Acceptance: acc:spawn-agents:E011-UNIT-002-verify-stage-raises-paste-did-not-land
# WMBT: wmbt:spawn-agents:E011
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E011-UNIT-002 — _verify_stage raises PasteDidNotLand when capture_pane_text
never shows the paste indicator or prompt prefix within the timeout.

RED: _verify_stage, PasteDidNotLand do not exist yet (issue #799).
"""
from __future__ import annotations

import pytest


class _NoPasteMux:
    """capture_pane_text always returns the idle state — paste never shows up."""

    def capture_pane_text(self, surface_ref: str) -> str:
        return "Press Enter to send"


def test_verify_stage_raises_paste_did_not_land_on_timeout():
    from atdd.coach.commands.spawn import (
        PasteDidNotLand,
        _verify_stage,
    )

    mux = _NoPasteMux()
    with pytest.raises(PasteDidNotLand):
        _verify_stage(
            stage_name="paste-landed",
            surface_ref="surface:2",
            backend=mux,
            expect_any=("paste again to expand", "You are the planner"),
            timeout_s=0.1,
            poll_interval_s=0.01,
        )


def test_verify_stage_passes_when_paste_indicator_appears():
    from atdd.coach.commands.spawn import _verify_stage

    class _PastedMux:
        def capture_pane_text(self, surface_ref: str) -> str:
            return "paste again to expand · 1 line"

    _verify_stage(
        stage_name="paste-landed",
        surface_ref="surface:2",
        backend=_PastedMux(),
        expect_any=("paste again to expand", "You are the planner"),
        timeout_s=1.0,
        poll_interval_s=0.01,
    )


def test_verify_stage_passes_when_prompt_prefix_appears():
    from atdd.coach.commands.spawn import _verify_stage

    class _PromptPrefixMux:
        def capture_pane_text(self, surface_ref: str) -> str:
            return "You are the planner agent for issue #799.\nYour role is..."

    _verify_stage(
        stage_name="paste-landed",
        surface_ref="surface:2",
        backend=_PromptPrefixMux(),
        expect_any=("paste again to expand", "You are the planner"),
        timeout_s=1.0,
        poll_interval_s=0.01,
    )


def test_paste_did_not_land_is_a_worker_readiness_timeout():
    """PasteDidNotLand should subclass WorkerReadinessTimeout for consistent handling."""
    from atdd.coach.commands.spawn import PasteDidNotLand, WorkerReadinessTimeout

    assert issubclass(PasteDidNotLand, WorkerReadinessTimeout)
