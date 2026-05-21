# URN: test:spawn-agents:spawn-time-non-interactive-convention:M001-UNIT-001-apply-canonical-name-no-slash-rename-injection
# Acceptance: acc:spawn-agents:M001-UNIT-001-apply-canonical-name-no-slash-rename-injection
"""M001-UNIT-001 — apply_canonical_name_and_layout does NOT call paste_text with /rename.

RED: session_naming_apply.py:91 calls backend.paste_text(ref, f'/rename {name}\\n').
GREEN: that call is removed; the function relies on backend.rename() for window title
only; Claude session naming is delegated to the shim (#824).
"""
import pytest
from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout


class FakeMultiplexer:
    def __init__(self, has_rename: bool = False):
        self.paste_calls: list[dict] = []
        self.send_key_calls: list[dict] = []
        self.rename_calls: list[dict] = []
        self._has_rename = has_rename

    def paste_text(self, ref: str, text: str) -> None:
        self.paste_calls.append({"ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.send_key_calls.append({"ref": ref, "key": key})

    def rename(self, ref: str, name: str) -> None:
        if not self._has_rename:
            raise AttributeError("rename not supported")
        self.rename_calls.append({"ref": ref, "name": name})

    def capture_pane_text(self, ref: str) -> str:
        return ""


def test_no_paste_text_with_slash_rename_no_native_rename():
    """With no native rename(), paste_text must NOT inject /rename (M001)."""
    backend = FakeMultiplexer(has_rename=False)
    apply_canonical_name_and_layout(backend, "surface:1", "ATDD829", surface_count=1)
    slash_rename_calls = [c for c in backend.paste_calls if "/rename" in c["text"]]
    assert not slash_rename_calls, (
        f"apply_canonical_name_and_layout called paste_text with '/rename' after M001 — "
        f"slash-command injection must be removed. Calls: {slash_rename_calls}"
    )


def test_no_paste_text_with_slash_rename_with_native_rename():
    """Even with native rename(), paste_text must NOT inject /rename (M001)."""
    backend = FakeMultiplexer(has_rename=True)
    apply_canonical_name_and_layout(backend, "surface:1", "ATDD829", surface_count=1)
    slash_rename_calls = [c for c in backend.paste_calls if "/rename" in c["text"]]
    assert not slash_rename_calls, (
        f"apply_canonical_name_and_layout called paste_text with '/rename' even when "
        f"native rename is available. M001 removes all slash injection. Calls: {slash_rename_calls}"
    )


def test_no_standalone_send_key_enter_after_rename():
    """No standalone send_key('Enter') for the rename path (M001 removes the full injection)."""
    backend = FakeMultiplexer(has_rename=False)
    apply_canonical_name_and_layout(backend, "surface:1", "ATDD829", surface_count=1)
    enter_calls = [c for c in backend.send_key_calls if c.get("key") == "Enter"]
    assert not enter_calls, (
        f"apply_canonical_name_and_layout still calls send_key('Enter') after M001 — "
        f"the rename submit key must be removed along with the injection. Calls: {enter_calls}"
    )
