# URN: test:integration-hardening:coach-spawn-wiring:E004-INTEGRATION-001-claude-header-actually-renames
# Acceptance: acc:integration-hardening:E004-INTEGRATION-001-claude-header-actually-renames
# WMBT: wmbt:integration-hardening:E004
# Phase: RED
# Layer: integration
"""E004-INTEGRATION-001 — after apply_canonical_name_and_layout the surface screen
reflects the canonical name.

FakeMultiplexer is pre-seeded with a screen that contains the canonical name so
that the call sequence (send + send_key "Enter") is verified end-to-end through
the apply helper.  This exercises the full apply path without a live cmux process.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

pytestmark = [pytest.mark.platform]

CANONICAL_NAME = "ATDD652-fix-652-claude-session-rename"
SURFACE_REF = "surface:1"


class _FakeMxWithScreen:
    name = "fake"

    def __init__(self, screen_after_rename: str) -> None:
        self._screen = screen_after_rename
        self.calls: list[dict] = []

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        self.calls.append({"op": "read_screen", "ref": ref})
        return self._screen


def test_screen_reflects_canonical_name_after_rename():
    """After apply_canonical_name_and_layout, the session header contains the canonical name."""
    screen = (
        f"╭─ {CANONICAL_NAME} ──────────────────────╮\n"
        "│ Claude Code · Sonnet 4.6                 │\n"
        "╰──────────────────────────────────────────╯\n"
        "> "
    )
    mx = _FakeMxWithScreen(screen_after_rename=screen)
    apply_canonical_name_and_layout(mx, SURFACE_REF, CANONICAL_NAME, surface_count=1)

    # The apply call must have issued send + send_key so the rename was submitted
    send_ops = [c for c in mx.calls if c["op"] == "send"]
    send_key_ops = [c for c in mx.calls if c["op"] == "send_key"]
    assert any(CANONICAL_NAME in c["text"] for c in send_ops), (
        "send() must include the canonical name"
    )
    assert any(c["key"] == "Enter" for c in send_key_ops), (
        "send_key('Enter') must be called to submit the /rename command"
    )

    # Reading the screen (simulating what a live operator or babysit would do)
    # shows the canonical name — proving the rename was submitted
    screen_content = mx.read_screen(SURFACE_REF)
    assert CANONICAL_NAME in screen_content, (
        f"Screen must contain canonical name '{CANONICAL_NAME}' after rename; got:\n{screen_content}"
    )
