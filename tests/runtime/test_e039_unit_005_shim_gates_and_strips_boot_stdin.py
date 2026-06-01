# URN: test:govern-lifecycle:extract-runtime-agent-control-and-close-spawn-cluster:E039-UNIT-005-shim-gates-and-strips-boot-stdin
# Acceptance: acc:govern-lifecycle:E039-UNIT-005-shim-gates-and-strips-boot-stdin
# WMBT: wmbt:govern-lifecycle:E039
# Phase: RED
# Assertion: behavioral
# Layer: runtime
"""E039-UNIT-005 — shim gates + strips boot-time stdin (issue #948).

The shim must not forward interactive-terminal chatter into the wrapped agent
CLI during boot. A cmux/ghostty terminal emits an unsolicited focus event
(``ESC[I`` / ``ESC[O``) on focus change at spawn time; forwarded into Claude
Code's kitty keyboard-protocol handshake it corrupts the boot and wedges the
TUI (the coach-spawned-agent welcome-screen wedge). ``forward_stdin_once``
therefore (1) drains-and-drops operator stdin until the ready-gate opens and
(2) always strips focus events from the bytes it forwards.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _shim(tmp_path: Path, payload: bytes, sink: list, agent_id: str):
    from atdd.runtime.agent_control._shim import PersonaShim

    return PersonaShim(
        agent_id=agent_id,
        spawn_command=["true"],
        runtime_dir=tmp_path,
        stdin_source=io.BytesIO(payload),
        pty_write_sink=sink.append,
    )


def test_stdin_dropped_before_ready_gate(tmp_path):
    """Pre-ready stdin is drained and discarded — nothing reaches the pty."""
    captured: list[bytes] = []
    shim = _shim(tmp_path, b"hello", captured, "e039u005-pre")
    shim._ready_gate_open = False
    shim.forward_stdin_once()
    assert captured == [], "boot-time stdin must be dropped before the ready-gate opens"


def test_focus_events_stripped_after_ready_gate(tmp_path):
    """After ready, real keystrokes forward but focus events are stripped."""
    captured: list[bytes] = []
    shim = _shim(tmp_path, b"\x1b[Oab\x1b[Icd", captured, "e039u005-post")
    shim._ready_gate_open = True
    shim.forward_stdin_once()
    assert b"".join(captured) == b"abcd", (
        "focus events ESC[I / ESC[O must be stripped; real keystrokes kept"
    )
