# URN: test:observe-and-correct:E006-UNIT-001-run-loop-includes-stdin-in-select-when-isatty
# Acceptance: acc:observe-and-correct:E006-UNIT-001-run-loop-includes-stdin-in-select-when-isatty
# WMBT: wmbt:observe-and-correct:E006
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E006-UNIT-001 — _run_loop adds sys.stdin.fileno() to the select watch list
when stdin_source.isatty() is True and calls forward_stdin_once() when stdin
becomes readable, forwarding operator keystrokes to the wrapped process pty.

Before implementation: _run_loop only watches master_fd in select(). The stdin fd
is never included, so forward_stdin_once() is never called from the loop, and
operator keystrokes are silently swallowed. Both tests below FAIL (RED).

Issue #861.
"""
from __future__ import annotations

import os
import select as stdlib_select
import threading

import pytest

pytestmark = [pytest.mark.platform]


class _FakeStdinTTY:
    """Fake stdin_source: pipe-backed with isatty()=True and a real fileno()."""

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


def test_run_loop_includes_stdin_fd_in_select_when_isatty(tmp_path, monkeypatch):
    """_run_loop must pass stdin_source.fileno() in the select() rlist when isatty() is True.

    RED assertion: current code calls select([master_fd], …) only — stdin fd is
    absent → assertion fails.
    """
    from atdd.coach.shim import PersonaShim

    r_fd, w_fd = os.pipe()
    os.write(w_fd, b"hello operator\n")

    select_rlists: list[list[int]] = []
    original_select = stdlib_select.select

    def recording_select(rlist, wlist, xlist, timeout=None):
        select_rlists.append(list(rlist))
        return original_select(rlist, wlist, xlist, timeout if timeout is not None else 0.0)

    monkeypatch.setattr(stdlib_select, "select", recording_select)

    shim = PersonaShim(
        agent_id="e005-unit-001-select",
        spawn_command=["python3", "-c", "import time; time.sleep(0.4)"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: None,
        stdin_source=_FakeStdinTTY(r_fd),
    )

    thread = threading.Thread(target=shim.run, kwargs={"timeout": 0.6}, daemon=True)
    thread.start()
    thread.join(timeout=3.0)

    os.close(r_fd)
    os.close(w_fd)

    assert any(r_fd in rlist for rlist in select_rlists), (
        f"stdin fd {r_fd!r} was never included in any select() rlist. "
        f"Current code omits stdin from the watch list — this is the RED gap. "
        f"Observed rlists (first 5): {select_rlists[:5]}"
    )


def test_run_loop_forwards_stdin_bytes_to_pty_when_isatty(tmp_path):
    """Bytes written to stdin_source appear in pty_write_sink during _run_loop.

    RED assertion: before implementation forward_stdin_once() is never called
    from _run_loop → pty_write_sink stays empty → assertion fails.
    """
    from atdd.coach.shim import PersonaShim

    sentinel = b"hello operator\n"
    r_fd, w_fd = os.pipe()
    os.write(w_fd, sentinel)

    pty_writes: list[bytes] = []

    shim = PersonaShim(
        agent_id="e005-unit-001-bytes",
        spawn_command=["python3", "-c", "import time; time.sleep(0.6)"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: pty_writes.append(data),
        stdin_source=_FakeStdinTTY(r_fd),
    )

    thread = threading.Thread(target=shim.run, kwargs={"timeout": 0.8}, daemon=True)
    thread.start()
    thread.join(timeout=3.0)

    os.close(r_fd)
    os.close(w_fd)

    forwarded = b"".join(pty_writes)
    assert sentinel in forwarded, (
        f"Operator keystrokes were not forwarded to pty via _run_loop. "
        f"Expected {sentinel!r} in pty_write_sink; got: {forwarded!r}"
    )


def test_run_loop_does_not_swallow_or_duplicate_stdin_bytes(tmp_path):
    """Each byte from stdin_source is forwarded exactly once — no loss, no duplication.

    RED assertion: before implementation pty_write_sink is empty (count==0 ≠ 1).
    """
    from atdd.coach.shim import PersonaShim

    sentinel = b"unique-sentinel-e005\n"
    r_fd, w_fd = os.pipe()
    os.write(w_fd, sentinel)

    pty_writes: list[bytes] = []

    shim = PersonaShim(
        agent_id="e005-unit-001-nodup",
        spawn_command=["python3", "-c", "import time; time.sleep(0.6)"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: pty_writes.append(data),
        stdin_source=_FakeStdinTTY(r_fd),
    )

    thread = threading.Thread(target=shim.run, kwargs={"timeout": 0.8}, daemon=True)
    thread.start()
    thread.join(timeout=3.0)

    os.close(r_fd)
    os.close(w_fd)

    forwarded = b"".join(pty_writes)
    count = forwarded.count(sentinel)
    assert count == 1, (
        f"Sentinel {sentinel!r} must appear exactly once in pty output. "
        f"count={count}, full output: {forwarded!r}"
    )
