# URN: test:observe-and-correct:E003-UNIT-009-operator-keystrokes-forwarded
# Acceptance: acc:observe-and-correct:E003-UNIT-009-operator-keystrokes-forwarded
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E003-UNIT-009 — The shim forwards operator keystrokes (shim stdin) to the
agent CLI pty master fd so a human can still attach and type.

Issue #824.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_shim_accepts_stdin_source_kwarg():
    """PersonaShim constructor accepts a stdin_source keyword argument."""
    from atdd.coach.shim import PersonaShim

    class FakeStdin:
        def read(self, n):
            return b""

    shim = PersonaShim(
        agent_id="keystroke-test",
        spawn_command=["sleep", "60"],
        runtime_dir=None,  # not needed for this test
        stdin_source=FakeStdin(),
    )
    assert shim is not None


def test_operator_keystrokes_forwarded_to_pty(tmp_path):
    """Bytes written to shim stdin are forwarded to the pty master fd."""
    from atdd.coach.shim import PersonaShim

    agent_id = "keystroke-forward-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    pty_writes: list[bytes] = []
    stdin_bytes = b"hello operator\n"

    class FakeStdin:
        def __init__(self):
            self._sent = False

        def read(self, n: int) -> bytes:
            if not self._sent:
                self._sent = True
                return stdin_bytes
            return b""

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: pty_writes.append(data),
        stdin_source=FakeStdin(),
    )

    # Forward one stdin read-cycle
    shim.forward_stdin_once()

    assert stdin_bytes in pty_writes, (
        f"Operator keystrokes not forwarded to pty. Got: {pty_writes!r}"
    )


def test_keystroke_forwarding_does_not_duplicate(tmp_path):
    """Each byte from stdin is forwarded exactly once (no duplication)."""
    from atdd.coach.shim import PersonaShim

    agent_id = "keystroke-nodup-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    pty_writes: list[bytes] = []
    call_count = [0]

    class CountingStdin:
        def read(self, n: int) -> bytes:
            call_count[0] += 1
            if call_count[0] == 1:
                return b"x"
            return b""

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: pty_writes.append(data),
        stdin_source=CountingStdin(),
    )

    shim.forward_stdin_once()
    shim.forward_stdin_once()

    total = b"".join(pty_writes)
    assert total == b"x", f"Expected single 'x' byte, got {total!r}"
