# URN: test:spawn-agents:coach-spawn-step-by-step-verify-each-stage:E011-UNIT-005-apply-canonical-name-verify-after-send
# Acceptance: acc:spawn-agents:E011-UNIT-005-apply-canonical-name-verify-after-send
# WMBT: wmbt:spawn-agents:E011
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E011-UNIT-005 — apply_canonical_name_and_layout accepts a verify_after_send
parameter; when True it calls capture_pane_text after /rename and raises
RenameNotAccepted if the canonical name does not appear within the timeout.

RED: apply_canonical_name_and_layout does not accept verify_after_send yet (issue #799).
The current implementation is fire-and-forget with no post-condition probe.
"""
from __future__ import annotations

import pytest


class _NeverShowsRenameMux:
    """Backend that accepts /rename but capture_pane_text never shows the new name."""

    def __init__(self):
        self.sends = []
        self.keys = []

    def rename(self, ref, name):
        pass

    def send(self, ref, text):
        self.sends.append((ref, text))

    def send_key(self, ref, key):
        self.keys.append((ref, key))

    def capture_pane_text(self, surface_ref: str) -> str:
        return "Press Enter to send"  # old name still showing


class _ShowsRenameAfterSendMux:
    """Backend whose capture_pane_text shows the post-submit acknowledgment immediately.

    E012: The gate now requires 'Session renamed to: <name>', not bare canonical name.
    """

    def __init__(self):
        self.paste_calls = []
        self.sends = []
        self.keys = []

    def rename(self, ref, name):
        pass

    def paste_text(self, ref, text):
        self.paste_calls.append((ref, text))

    def send(self, ref, text):
        self.sends.append((ref, text))

    def send_key(self, ref, key):
        self.keys.append((ref, key))

    def capture_pane_text(self, surface_ref: str) -> str:
        return "Session renamed to: ATDD42"


def test_apply_canonical_name_raises_rename_not_accepted_when_verify_after_send_true():
    """M001 (#829): verify_after_send=True is now a no-op; must NOT raise RenameNotAccepted."""
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mux = _NeverShowsRenameMux()
    # Post-M001: /rename injection removed; verify_after_send is accepted but ignored.
    apply_canonical_name_and_layout(
        backend=mux,
        ref="surface:1",
        canonical_name="ATDD42",
        surface_count=1,
        verify_after_send=True,
        verify_timeout_s=0.1,
        verify_poll_s=0.01,
    )


def test_apply_canonical_name_passes_when_rename_appears_in_capture():
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mux = _ShowsRenameAfterSendMux()
    # Should not raise — canonical name appears in capture_pane_text immediately.
    apply_canonical_name_and_layout(
        backend=mux,
        ref="surface:1",
        canonical_name="ATDD42",
        surface_count=1,
        verify_after_send=True,
        verify_timeout_s=1.0,
        verify_poll_s=0.01,
    )


def test_apply_canonical_name_does_not_verify_when_verify_after_send_false():
    """Default (no verify_after_send) behaves as before — no capture probe."""
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    # _NeverShowsRenameMux would cause a failure if probe happened; with
    # verify_after_send=False (the default) no probe occurs.
    mux = _NeverShowsRenameMux()
    apply_canonical_name_and_layout(
        backend=mux,
        ref="surface:1",
        canonical_name="ATDD42",
        surface_count=1,
        # verify_after_send defaults to False — no probe
    )
