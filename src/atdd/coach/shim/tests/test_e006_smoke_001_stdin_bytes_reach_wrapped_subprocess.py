# URN: test:observe-and-correct:E006-SMOKE-001-stdin-bytes-reach-wrapped-subprocess
# Acceptance: acc:observe-and-correct:E006-SMOKE-001-stdin-bytes-reach-wrapped-subprocess
# WMBT: wmbt:observe-and-correct:E006
# Phase: SMOKE
# Assertion: behavioral
# Layer: integration
"""E006-SMOKE-001 — End-to-end round-trip: PersonaShim wrapping a real
echo subprocess receives operator keystrokes from its stdin_source and the
subprocess echoes them back through the pty output chain.

Round-trip path:
  test writes to pipe → stdin_source.read() → forward_stdin_once() →
  pty master fd → subprocess stdin (pty slave) → subprocess stdout (pty slave) →
  pty master fd → stdout_sink → assertion passes

Before implementation: _run_loop never reads from stdin_source, so the
subprocess never receives the sentinel bytes, never echoes them, and the
assertion fails within the 5-second deadline (RED / SMOKE-RED).

Issue #861.
"""
from __future__ import annotations

import os
import threading
import time

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.platform]

_ECHO_SCRIPT = (
    "import sys\n"
    "line = sys.stdin.readline()\n"
    "sys.stdout.write('GOT:' + line)\n"
    "sys.stdout.flush()\n"
)


class _FakeStdinTTY:
    """Pipe-backed stdin_source that reports isatty()=True.

    Using a real pipe avoids PTY-within-PTY complexity while still allowing
    the shim to correctly identify it as a TTY for the isatty() guard.
    """

    def __init__(self, fd: int) -> None:
        self._fd = fd

    def read(self, n: int) -> bytes:
        try:
            return os.read(self._fd, n)
        except OSError:
            return b""

    def isatty(self) -> bool:
        return True

    def fileno(self) -> int:
        return self._fd


def test_stdin_bytes_reach_wrapped_subprocess(tmp_path):
    """Sentinel bytes written to shim stdin appear in shim stdout (via echo subprocess).

    The subprocess reads one line from its stdin and prefixes it with 'GOT:'.
    The shim must forward operator stdin bytes to the subprocess's pty stdin for
    the echo to appear in stdout_sink within 5 seconds.

    FAILS before implementation: stdin fd absent from select → no forwarding →
    subprocess never receives sentinel → stdout_sink never contains 'GOT:'.
    """
    from atdd.coach.shim import PersonaShim

    sentinel = b"ATDD_E006_SENTINEL\n"
    r_fd, w_fd = os.pipe()

    stdout_captured: list[bytes] = []

    shim = PersonaShim(
        agent_id="e005-integration-001",
        spawn_command=["python3", "-c", _ECHO_SCRIPT],
        runtime_dir=tmp_path,
        stdin_source=_FakeStdinTTY(r_fd),
        stdout_sink=lambda data: stdout_captured.append(data),
    )

    thread = threading.Thread(target=shim.run, kwargs={"timeout": 6.0}, daemon=True)
    thread.start()

    # Brief pause for shim + subprocess to initialise
    time.sleep(0.15)

    # Write operator keystrokes into the shim's stdin pipe
    os.write(w_fd, sentinel)

    # Poll for the echo within 5 seconds
    deadline = time.time() + 5.0
    found = False
    while time.time() < deadline:
        captured = b"".join(stdout_captured)
        if b"GOT:" in captured:
            found = True
            break
        time.sleep(0.05)

    thread.join(timeout=2.0)

    os.close(r_fd)
    os.close(w_fd)

    captured = b"".join(stdout_captured)
    assert found, (
        f"Sentinel bytes did not complete the operator→shim→subprocess→stdout "
        f"round-trip within 5 seconds. "
        f"stdout_sink content: {captured!r}. "
        f"This confirms E006: stdin fd is absent from _run_loop's select() watch list."
    )
    assert b"ATDD_E006_SENTINEL" in captured, (
        f"'GOT:' marker present but sentinel payload missing. Got: {captured!r}"
    )


def test_no_bytes_lost_or_duplicated_in_round_trip(tmp_path):
    """The sentinel appears exactly once in the echo output — no byte loss or duplication.

    Validates that forward_stdin_once() is called exactly once per select-readable
    event and that os.write to the pty master fd is atomic for small payloads.

    FAILS before implementation: sentinel count is 0 (not 1).
    """
    from atdd.coach.shim import PersonaShim

    sentinel = b"UNIQUE_PAYLOAD_E006\n"
    r_fd, w_fd = os.pipe()

    stdout_captured: list[bytes] = []

    shim = PersonaShim(
        agent_id="e005-integration-001-nodup",
        spawn_command=["python3", "-c", _ECHO_SCRIPT],
        runtime_dir=tmp_path,
        stdin_source=_FakeStdinTTY(r_fd),
        stdout_sink=lambda data: stdout_captured.append(data),
    )

    thread = threading.Thread(target=shim.run, kwargs={"timeout": 6.0}, daemon=True)
    thread.start()

    time.sleep(0.15)
    os.write(w_fd, sentinel)

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if b"GOT:" in b"".join(stdout_captured):
            break
        time.sleep(0.05)

    thread.join(timeout=2.0)

    os.close(r_fd)
    os.close(w_fd)

    captured = b"".join(stdout_captured)
    # The sentinel payload should appear at most once in the subprocess echo output.
    # (Terminal echo of the forwarded bytes may also appear; we count only the
    # subprocess-added 'GOT:' prefix lines.)
    got_lines = [line for line in captured.split(b"\n") if line.startswith(b"GOT:")]
    assert len(got_lines) >= 1, (
        f"No 'GOT:' echo lines found. Forwarding did not occur. "
        f"Full output: {captured!r}"
    )
    payload_count = sum(1 for line in got_lines if b"UNIQUE_PAYLOAD_E006" in line)
    assert payload_count == 1, (
        f"Sentinel payload appeared in {payload_count} 'GOT:' lines (expected 1). "
        f"GOT lines: {got_lines!r}"
    )
