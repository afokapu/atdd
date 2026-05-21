# URN: test:spawn-agents:coach-spawn-rename-enter-races-text-send:E012-UNIT-001-atomic-rename-send-no-separate-enter
# Acceptance: acc:spawn-agents:E012-UNIT-001-atomic-rename-send-no-separate-enter
# WMBT: wmbt:spawn-agents:E012
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E012-UNIT-001 — apply_canonical_name_and_layout sends /rename as a single
atomic paste_text call with a trailing newline, not two separate send + send_key
calls; no standalone send_key('Enter') follows the rename injection.

RED: apply_canonical_name_and_layout currently calls backend.send(ref, '/rename X')
then backend.send_key(ref, 'Enter') as two unsynced cmux subprocess calls (issue #811).
The fix replaces this with backend.paste_text(ref, '/rename X\\n') so the rename text
and submit land atomically in a single input event.
"""
from __future__ import annotations

import pytest


class _RecordingMux:
    """Records paste_text and send_key calls; implements rename so the
    backend-rename path does not raise AttributeError."""

    def __init__(self):
        self.paste_calls: list[tuple[str, str]] = []
        self.send_key_calls: list[tuple[str, str]] = []
        self.send_calls: list[tuple[str, str]] = []

    def rename(self, ref: str, name: str) -> None:
        pass

    def send(self, ref: str, text: str) -> None:
        self.send_calls.append((ref, text))

    def send_key(self, ref: str, key: str) -> None:
        self.send_key_calls.append((ref, key))

    def paste_text(self, ref: str, text: str) -> None:
        self.paste_calls.append((ref, text))


def test_apply_canonical_name_uses_paste_text_with_trailing_newline():
    """M001 (#829): /rename injection removed — paste_text must NOT be called with '/rename'.

    Updated from E012: the atomic paste_text('/rename X\\n') fix (E012) is superseded
    by M001 which removes the entire /rename injection. The invariant is now that
    paste_text is NOT called with any '/rename' payload at all.
    """
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mux = _RecordingMux()
    apply_canonical_name_and_layout(
        backend=mux,
        ref="surface:1",
        canonical_name="ATDD42",
        surface_count=1,
    )

    rename_pastes = [
        text for _ref, text in mux.paste_calls
        if "/rename ATDD42" in text
    ]
    assert not rename_pastes, (
        "paste_text was called with a '/rename ATDD42' payload after M001 removal — "
        "apply_canonical_name_and_layout must NOT inject /rename (M001, issue #829). "
        f"Got: {rename_pastes}"
    )


def test_apply_canonical_name_does_not_send_standalone_enter_for_rename():
    """No send_key('Enter') call follows the rename injection (it is part of the paste)."""
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mux = _RecordingMux()
    apply_canonical_name_and_layout(
        backend=mux,
        ref="surface:1",
        canonical_name="ATDD42",
        surface_count=1,
    )

    enter_after_rename = [
        (ref, key) for ref, key in mux.send_key_calls
        if key == "Enter"
    ]
    assert not enter_after_rename, (
        "send_key('Enter') was called as a standalone follow-up to the rename "
        "injection; with atomic paste_text the Enter is embedded in the payload "
        "and send_key must NOT be issued separately (E012, issue #811). "
        f"Got send_key calls: {mux.send_key_calls}"
    )


def test_apply_canonical_name_does_not_use_send_for_rename():
    """backend.send is NOT used for the /rename command (paste_text replaces it)."""
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mux = _RecordingMux()
    apply_canonical_name_and_layout(
        backend=mux,
        ref="surface:1",
        canonical_name="ATDD42",
        surface_count=1,
    )

    rename_sends = [
        (ref, text) for ref, text in mux.send_calls
        if "/rename" in text
    ]
    assert not rename_sends, (
        "backend.send was called with a '/rename' payload; the atomic paste_text "
        "pattern must replace send for the rename injection (E012, issue #811). "
        f"Got send calls: {mux.send_calls}"
    )


def test_apply_canonical_name_paste_text_called_exactly_once_for_rename():
    """M001 (#829): /rename injection removed — paste_text must have zero /rename calls.

    Updated from E012: post-M001 there must be zero paste_text calls containing '/rename',
    not exactly one.
    """
    from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

    mux = _RecordingMux()
    apply_canonical_name_and_layout(
        backend=mux,
        ref="surface:1",
        canonical_name="ATDD42",
        surface_count=1,
    )

    rename_pastes = [
        text for _ref, text in mux.paste_calls
        if "/rename" in text
    ]
    assert len(rename_pastes) == 0, (
        f"Expected zero paste_text calls for /rename after M001 removal, got {len(rename_pastes)}: "
        f"{rename_pastes}"
    )
