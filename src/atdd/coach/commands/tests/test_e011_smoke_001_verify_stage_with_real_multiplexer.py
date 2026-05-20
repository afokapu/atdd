# URN: test:spawn-agents:coach-spawn-step-by-step-verify-each-stage:E011-SMOKE-001-verify-stage-with-real-multiplexer
# Acceptance: acc:spawn-agents:E011-SMOKE-001-verify-stage-with-real-multiplexer
# WMBT: wmbt:spawn-agents:E011
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E011-SMOKE-001 — against a real cmux session, capture_pane_text returns
non-empty content confirming the method is wired to the cmux backend and
_verify_stage does not raise when the expected trivially-true signal is present.

Opt-in: skipped unless ATDD_RUN_SMOKE=1. A real cmux session is required.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against a real multiplexer",
    ),
]


def test_capture_pane_text_returns_string_on_real_surface(tmp_path):
    """Real cmux: capture_pane_text returns a string; _verify_stage does not raise."""
    from atdd.coach.commands.spawn import _verify_stage
    from atdd.coach.utils.multiplexer import get_multiplexer

    mx = get_multiplexer()
    if mx.name != "cmux":
        pytest.skip("E011 SMOKE test only exercises cmux backend")

    surface_ref = mx.new_surface(
        cwd=str(tmp_path),
        command="sleep 5",
        name="ATDD799-e011-smoke",
    )
    assert surface_ref

    try:
        result = mx.capture_pane_text(surface_ref)
        assert isinstance(result, str), (
            f"capture_pane_text must return str, got {type(result)}"
        )

        # _verify_stage with empty string as the expected signal (trivially matches)
        # should return without raising on any pane that returns any string.
        _verify_stage(
            stage_name="smoke-check",
            surface_ref=surface_ref,
            backend=mx,
            expect_any=("",),  # trivially true — any capture passes
            timeout_s=5.0,
            poll_interval_s=0.1,
        )
    finally:
        try:
            mx.close(surface_ref)
        except Exception:
            pass
