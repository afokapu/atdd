# URN: test:integration-hardening:E004-UNIT-001-rename-submits-via-send_key
# Acceptance: acc:integration-hardening:E004-UNIT-001-rename-submits-via-send_key
# WMBT: wmbt:integration-hardening:E004
# Phase: RED
# Layer: application
"""E004-UNIT-001 — apply_canonical_name_and_layout does NOT use send or send_key for rename.

M001 (#829): the /rename slash-command injection has been removed entirely.
apply_canonical_name_and_layout now calls only backend.rename() for the tab/window
title and never emits send() or send_key() calls for the rename path.

Updated from the original E004 guard (issue #652 bare-newline regression) which
verified the two-call pattern. The two-call pattern is superseded by M001.
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
    """M001 (#829): no send() or send_key() calls for the rename path post-M001."""
    mx = _FakeMx()
    apply_canonical_name_and_layout(mx, SURFACE_REF, CANONICAL_NAME, surface_count=1)

    send_ops = [c for c in mx.calls if c["op"] == "send"]
    send_key_ops = [c for c in mx.calls if c["op"] == "send_key"]

    assert len(send_ops) == 0, (
        f"send() must NOT be called after M001 /rename removal. Got: {send_ops}"
    )
    assert len(send_key_ops) == 0, (
        f"send_key() must NOT be called after M001 /rename removal. Got: {send_key_ops}"
    )


def test_send_precedes_send_key():
    """M001 (#829): no send or send_key operations emitted for the rename path."""
    mx = _FakeMx()
    apply_canonical_name_and_layout(mx, SURFACE_REF, CANONICAL_NAME, surface_count=1)

    ops = [c["op"] for c in mx.calls if c["op"] in ("send", "send_key")]
    assert not ops, (
        f"No send/send_key operations should be emitted after M001. Got: {ops}"
    )


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
