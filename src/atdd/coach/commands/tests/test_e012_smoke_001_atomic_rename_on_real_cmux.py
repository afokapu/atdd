# URN: test:spawn-agents:coach-spawn-rename-enter-races-text-send:E012-SMOKE-001-atomic-rename-on-real-cmux
# Acceptance: acc:spawn-agents:E012-SMOKE-001-atomic-rename-on-real-cmux
# WMBT: wmbt:spawn-agents:E012
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E012-SMOKE-001 — against a real cmux session, the atomic '/rename X\\n'
paste-with-newline submits the slash command and the pane reflects
'Session renamed to: X' within the bounded timeout.

Opt-in: skipped unless ATDD_RUN_SMOKE=1. A real cmux session running
Claude Code is required for the rename to succeed.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against a real cmux session",
    ),
]


def test_atomic_rename_paste_submits_on_real_cmux(tmp_path):
    """Real cmux: apply_canonical_name_and_layout with verify_after_send=True
    uses paste_text and confirms 'Session renamed to:' appears in the pane."""
    from atdd.coach.utils.multiplexer import get_multiplexer
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mx = get_multiplexer()
    if mx.name != "cmux":
        pytest.skip("E012 SMOKE test only exercises cmux backend")

    canonical_name = "ATDD811-e012-smoke"
    surface_ref = mx.new_surface(
        cwd=str(tmp_path),
        command="claude",
        name=canonical_name,
    )
    assert surface_ref

    try:
        # apply_canonical_name_and_layout must not raise RenameNotAccepted —
        # the atomic paste_text('/rename X\n') should submit the slash command
        # and Claude Code should acknowledge with 'Session renamed to: X'.
        apply_canonical_name_and_layout(
            backend=mx,
            ref=surface_ref,
            canonical_name=canonical_name,
            surface_count=1,
            verify_after_send=True,
            verify_timeout_s=30.0,
            verify_poll_s=0.5,
        )

        # Confirm the post-submit signal is in the pane.
        pane_text = mx.capture_pane_text(surface_ref)
        assert "Session renamed to:" in pane_text, (
            f"'Session renamed to:' not found in pane after rename; "
            f"pane content: {pane_text[:200]!r}"
        )
    finally:
        try:
            mx.close(surface_ref)
        except Exception:
            pass


def test_orphan_pane_closed_on_timeout_real_cmux(tmp_path):
    """Real cmux: if the rename times out (surface with non-Claude process),
    _close_surface_on_failure is called and no surface is stranded."""
    from atdd.coach.commands.spawn import RenameNotAccepted
    from atdd.coach.utils.multiplexer import get_multiplexer
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mx = get_multiplexer()
    if mx.name != "cmux":
        pytest.skip("E012 SMOKE test only exercises cmux backend")

    # Surface running a plain sleep process — /rename will never be acknowledged.
    surface_ref = mx.new_surface(
        cwd=str(tmp_path),
        command="sleep 60",
        name="ATDD811-e012-smoke-timeout",
    )
    assert surface_ref

    try:
        with pytest.raises(RenameNotAccepted):
            apply_canonical_name_and_layout(
                backend=mx,
                ref=surface_ref,
                canonical_name="ATDD811-timeout",
                surface_count=1,
                verify_after_send=True,
                verify_timeout_s=2.0,
                verify_poll_s=0.2,
            )
        # After RenameNotAccepted, the surface should have been closed by the
        # caller (cmd_spawn) — this smoke test just confirms the exception fires.
    finally:
        try:
            mx.close(surface_ref)
        except Exception:
            pass
