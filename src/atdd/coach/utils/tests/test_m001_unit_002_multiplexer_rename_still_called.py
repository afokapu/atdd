# URN: test:spawn-agents:spawn-time-non-interactive-convention:M001-UNIT-002-multiplexer-level-rename-still-called
# Acceptance: acc:spawn-agents:M001-UNIT-002-multiplexer-level-rename-still-called
"""M001-UNIT-002 — backend.rename() (window title) is still called; /rename paste is removed.

RED: currently paste_text('/rename X\n') replaces backend.rename() when available.
GREEN: backend.rename() is called for the tab/window title; no /rename paste happens.
"""
import pytest
from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout


class RecordingMux:
    def __init__(self):
        self.rename_calls: list[dict] = []
        self.paste_calls: list[dict] = []
        self.send_key_calls: list[dict] = []

    def rename(self, ref: str, name: str) -> None:
        self.rename_calls.append({"ref": ref, "name": name})

    def paste_text(self, ref: str, text: str) -> None:
        self.paste_calls.append({"ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.send_key_calls.append({"ref": ref, "key": key})

    def capture_pane_text(self, ref: str) -> str:
        return ""


def test_backend_rename_called_with_canonical_name():
    backend = RecordingMux()
    apply_canonical_name_and_layout(backend, "surface:1", "ATDD829", surface_count=1)
    assert len(backend.rename_calls) == 1, (
        f"backend.rename() must be called exactly once for the tab-title rename. "
        f"Calls: {backend.rename_calls}"
    )
    assert backend.rename_calls[0]["name"] == "ATDD829", (
        f"backend.rename() must be called with canonical_name='ATDD829'. "
        f"Got: {backend.rename_calls[0]}"
    )


def test_no_slash_rename_in_paste_when_native_rename_available():
    backend = RecordingMux()
    apply_canonical_name_and_layout(backend, "surface:1", "ATDD829", surface_count=1)
    slash_renames = [c for c in backend.paste_calls if "/rename" in c.get("text", "")]
    assert not slash_renames, (
        f"paste_text called with '/rename' even though backend supports native rename(). "
        f"M001: remove all /rename injection. Calls: {slash_renames}"
    )
