# URN: test:spawn-agents:coach-spawn-rename-enter-races-text-send:E012-UNIT-003-fake-mux-models-enter-races-text
# Acceptance: acc:spawn-agents:E012-UNIT-003-fake-mux-models-enter-races-text
# WMBT: wmbt:spawn-agents:E012
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E012-UNIT-003 — FakeMultiplexer can model the production race where Enter
lands before the typed text is registered: pane shows '❯ /rename ATDD42'
indefinitely, 'Session renamed to:' never appears. The new gate correctly
raises RenameNotAccepted; the OLD gate (expect_any=(canonical_name,)) would
have passed — demonstrating the false-positive the fix eliminates.

RED: apply_canonical_name_and_layout still uses the old expect_any=(canonical_name,)
check so the race scenario does NOT raise RenameNotAccepted today; the test that
calls apply_canonical_name_and_layout end-to-end with the race-scripted FakeMultiplexer
and expects RenameNotAccepted will FAIL (issue #811).
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.multiplexer import FakeMultiplexer


def _race_mux(canonical_name: str) -> FakeMultiplexer:
    """Build a FakeMultiplexer scripted to model the Enter-races-text failure.

    capture_pane_text always returns the typed-but-unsubmitted input line;
    'Session renamed to: <name>' never appears.
    """
    mux = FakeMultiplexer()
    # Script _pane_captures with a long repeating sequence of the false-positive
    # pane state.  Each call pops the front; when exhausted FakeMultiplexer
    # returns "".  We need enough to cover the verify_timeout_s poll window.
    mux._pane_captures = [f"❯ /rename {canonical_name}"] * 200
    return mux


def test_race_scenario_raises_rename_not_accepted_under_new_gate():
    """apply_canonical_name_and_layout raises RenameNotAccepted when the mux
    models the Enter-races-text race (canonical name visible but rename unsubmitted)."""
    from atdd.coach.commands.spawn import RenameNotAccepted
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mux = _race_mux("ATDD42")
    with pytest.raises(RenameNotAccepted):
        apply_canonical_name_and_layout(
            backend=mux,
            ref="surface:1",
            canonical_name="ATDD42",
            surface_count=1,
            verify_after_send=True,
            verify_timeout_s=0.1,
            verify_poll_s=0.01,
        )


def test_race_scenario_old_gate_would_not_raise():
    """Demonstrates the old bug: _verify_stage with expect_any=(canonical_name,)
    does NOT raise when the pane shows '❯ /rename ATDD42' — a false positive."""
    from atdd.coach.commands.spawn import RenameNotAccepted, _verify_stage

    class _RacePaneMux:
        def capture_pane_text(self, surface_ref: str) -> str:
            return "❯ /rename ATDD42"

    # Old check: any occurrence of the canonical name satisfies the gate.
    # The unsubmitted input line '❯ /rename ATDD42' contains 'ATDD42', so
    # _verify_stage does NOT raise — this is the false positive.
    _verify_stage(
        stage_name="rename-accepted",
        surface_ref="surface:1",
        backend=_RacePaneMux(),
        expect_any=("ATDD42",),   # old check — canonical name anywhere
        timeout_s=0.1,
        poll_interval_s=0.01,
    )
    # Reaching here proves the old check was a false positive for the race scenario.


def test_race_scenario_new_gate_raises_via_verify_stage_directly():
    """Calling _verify_stage directly with the new expect_any raises RenameNotAccepted
    for the same race-scenario pane content."""
    from atdd.coach.commands.spawn import RenameNotAccepted, _verify_stage

    class _RacePaneMux:
        def capture_pane_text(self, surface_ref: str) -> str:
            return "❯ /rename ATDD42"

    with pytest.raises(RenameNotAccepted):
        _verify_stage(
            stage_name="rename-accepted",
            surface_ref="surface:1",
            backend=_RacePaneMux(),
            expect_any=("Session renamed to: ATDD42",),  # new check — post-submit signal
            timeout_s=0.1,
            poll_interval_s=0.01,
        )


def test_fake_multiplexer_pane_captures_exhausted_returns_empty():
    """FakeMultiplexer returns empty string once _pane_captures is exhausted;
    the race mux helper provides enough captures to cover the polling window."""
    mux = FakeMultiplexer()
    mux._pane_captures = ["screen1", "screen2"]
    assert mux.capture_pane_text("surface:1") == "screen1"
    assert mux.capture_pane_text("surface:1") == "screen2"
    assert mux.capture_pane_text("surface:1") == ""  # exhausted
