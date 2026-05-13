# URN: test:integration-hardening:E004-UNIT-001-rename-submits-via-send_key
# Acceptance: acc:integration-hardening:E004-UNIT-001-rename-submits-via-send_key
# WMBT: wmbt:integration-hardening:E004
# Phase: RED
# Layer: application
"""E004-UNIT-001 — apply_canonical_name_and_layout uses send + send_key (no bare newline).

Asserts that the /rename slash command is split into two multiplexer calls:
  1. send(ref, "/rename <name>")  — no trailing newline
  2. send_key(ref, "Enter")       — synthesized key press

Regression guard for the bug described in issue #652 where send() was called
with a literal newline that Claude's REPL does not interpret as Enter.
"""
from __future__ import annotations

from typing import Optional

import pytest

from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout

pytestmark = [pytest.mark.coach]

CANONICAL_NAME = "ATDD582-issue-582"
SURFACE_REF = "surface:1"


class _FakeMx:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""


def test_rename_uses_send_then_send_key():
    mx = _FakeMx()
    apply_canonical_name_and_layout(mx, SURFACE_REF, CANONICAL_NAME, surface_count=1)

    send_ops = [c for c in mx.calls if c["op"] == "send"]
    send_key_ops = [c for c in mx.calls if c["op"] == "send_key"]

    assert len(send_ops) == 1
    assert send_ops[0]["text"] == f"/rename {CANONICAL_NAME}"
    assert "\n" not in send_ops[0]["text"], "send() must not contain a literal newline"

    assert len(send_key_ops) == 1
    assert send_key_ops[0]["key"] == "Enter"


def test_send_precedes_send_key():
    mx = _FakeMx()
    apply_canonical_name_and_layout(mx, SURFACE_REF, CANONICAL_NAME, surface_count=1)

    ops = [c["op"] for c in mx.calls if c["op"] in ("send", "send_key")]
    assert ops.index("send") < ops.index("send_key")


def test_send_targets_correct_ref():
    mx = _FakeMx()
    apply_canonical_name_and_layout(mx, SURFACE_REF, CANONICAL_NAME, surface_count=1)

    for call in mx.calls:
        if call["op"] in ("send", "send_key"):
            assert call["ref"] == SURFACE_REF


def test_empty_canonical_name_is_noop():
    mx = _FakeMx()
    apply_canonical_name_and_layout(mx, SURFACE_REF, "", surface_count=1)

    assert not any(c["op"] in ("send", "send_key") for c in mx.calls)
