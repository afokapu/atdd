# URN: test:spawn-agents:coach-spawn-rename-enter-races-text-send:E012-UNIT-002-rename-accepted-requires-post-submit-signal
# Acceptance: acc:spawn-agents:E012-UNIT-002-rename-accepted-requires-post-submit-signal
# WMBT: wmbt:spawn-agents:E012
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E012-UNIT-002 — apply_canonical_name_and_layout with verify_after_send=True
requires 'Session renamed to: <name>' in the pane capture rather than the bare
canonical name; typed-but-unsubmitted '❯ /rename ATDD42' does NOT satisfy the gate.

RED: apply_canonical_name_and_layout currently calls _verify_stage with
expect_any=(canonical_name,) which matches the canonical name anywhere in the pane
— including inside the unsubmitted '❯ /rename ATDD42' input line. The fix must
change the expect_any to ('Session renamed to: ATDD42',) so only the post-submit
acknowledgment satisfies the gate (issue #811).
"""
from __future__ import annotations

import pytest


class _FalsePositiveMux:
    """Simulates the race failure: capture_pane_text always returns the canonical name
    inside the unsubmitted input line ('❯ /rename ATDD42'), never the post-submit
    acknowledgment. Under the old check (expect_any=(canonical_name,)) this passes;
    under the new check (expect_any=('Session renamed to: ATDD42',)) it raises."""

    def __init__(self):
        self.paste_calls: list[tuple[str, str]] = []
        self.send_key_calls: list[tuple[str, str]] = []

    def rename(self, ref: str, name: str) -> None:
        pass

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        self.send_key_calls.append((ref, key))

    def paste_text(self, ref: str, text: str) -> None:
        self.paste_calls.append((ref, text))

    def capture_pane_text(self, surface_ref: str) -> str:
        # The pane shows the typed-but-unsubmitted rename: canonical name is present
        # as a substring but the slash command was never submitted.
        return "❯ /rename ATDD42"


class _PostSubmitMux:
    """Simulates successful rename: capture_pane_text returns the post-submit
    acknowledgment line that Claude Code emits after accepting /rename."""

    def __init__(self):
        self.paste_calls: list[tuple[str, str]] = []

    def rename(self, ref: str, name: str) -> None:
        pass

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        pass

    def paste_text(self, ref: str, text: str) -> None:
        self.paste_calls.append((ref, text))

    def capture_pane_text(self, surface_ref: str) -> str:
        return "Session renamed to: ATDD42"


class _StatusBarOnlyMux:
    """Simulates partial rename success: pane shows status bar with canonical name
    but NOT the 'Session renamed to:' acknowledgment line — this must NOT satisfy
    the tightened gate."""

    def rename(self, ref: str, name: str) -> None:
        pass

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        pass

    def paste_text(self, ref: str, text: str) -> None:
        pass

    def capture_pane_text(self, surface_ref: str) -> str:
        # Status bar may show canonical name after some partial rename events,
        # but the acknowledgment line has not appeared.
        return "─── ATDD42 ──────────────────────────────────────────────────────────"


def test_rename_accepted_gate_rejects_typed_but_unsubmitted_input():
    """apply_canonical_name_and_layout raises RenameNotAccepted when pane shows
    '❯ /rename ATDD42' (false positive under old check)."""
    from atdd.coach.commands.spawn import RenameNotAccepted
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mux = _FalsePositiveMux()
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


def test_rename_accepted_gate_passes_on_post_submit_acknowledgment():
    """apply_canonical_name_and_layout does NOT raise when pane shows
    'Session renamed to: ATDD42'."""
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mux = _PostSubmitMux()
    # Must not raise — the post-submit acknowledgment satisfies the gate.
    apply_canonical_name_and_layout(
        backend=mux,
        ref="surface:1",
        canonical_name="ATDD42",
        surface_count=1,
        verify_after_send=True,
        verify_timeout_s=1.0,
        verify_poll_s=0.01,
    )


def test_rename_accepted_gate_rejects_status_bar_only():
    """Status bar containing the canonical name (─── ATDD42 ──) does NOT
    satisfy the tightened gate; RenameNotAccepted must be raised."""
    from atdd.coach.commands.spawn import RenameNotAccepted
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mux = _StatusBarOnlyMux()
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
