# URN: test:observe-and-correct:E005-UNIT-002-stdin-not-added-when-not-isatty
# Acceptance: acc:observe-and-correct:E005-UNIT-002-stdin-not-added-when-not-isatty
# WMBT: wmbt:observe-and-correct:E005
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E005-UNIT-002 — When stdin_source.isatty() returns False (CI / subprocess
invocation), _run_loop must NOT include stdin_source.fileno() in the select
watch list, and the existing cli-return and pty-output paths must be unchanged.

This is a regression guard: adding stdin to the select loop must be gated on
isatty(). If the implementation ignores the TTY check, it may break CI where
stdin is a pipe or /dev/null, and may trigger reads on closed fds.

These tests are written at RED time. The non-TTY select-exclusion test
(test_run_loop_excludes_stdin_fd_from_select_when_not_isatty) may already pass
on the current unimplemented code (current code never adds stdin to select
regardless). It is included to catch regressions once implementation lands.
The cli-return delivery test documents existing behavior.

Issue #861.
"""
from __future__ import annotations

import json
import os
import select as stdlib_select
import threading
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


class _FakeStdinNonTTY:
    """Fake stdin_source: isatty()=False (simulates CI/pipe invocation)."""

    def __init__(self, fd: int) -> None:
        self._fd = fd
        self.read_count = 0

    def read(self, n: int) -> bytes:
        self.read_count += 1
        try:
            return os.read(self._fd, n)
        except OSError:
            return b""

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        return self._fd


def _write_cli_return(path: Path, correction_text: str) -> None:
    record = {
        "rule_id": "E005-TEST-RULE",
        "correction_text": correction_text,
        "severity": 3,
        "issued_at": "2026-05-26T00:00:00Z",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def test_run_loop_excludes_stdin_fd_from_select_when_not_isatty(tmp_path, monkeypatch):
    """_run_loop must NOT include stdin fd in select() when isatty() is False.

    Current code (before impl): stdin fd is never passed to select → this test
    passes as a pre-condition baseline. After impl it guards against the TTY
    check being missing and stdin being unconditionally added.
    """
    from atdd.coach.shim import PersonaShim

    r_fd, w_fd = os.pipe()

    select_rlists: list[list[int]] = []
    original_select = stdlib_select.select

    def recording_select(rlist, wlist, xlist, timeout=None):
        select_rlists.append(list(rlist))
        return original_select(rlist, wlist, xlist, timeout if timeout is not None else 0.0)

    monkeypatch.setattr(stdlib_select, "select", recording_select)

    shim = PersonaShim(
        agent_id="e005-unit-002-exclude",
        spawn_command=["python3", "-c", "import time; time.sleep(0.4)"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: None,
        stdin_source=_FakeStdinNonTTY(r_fd),
    )

    thread = threading.Thread(target=shim.run, kwargs={"timeout": 0.6}, daemon=True)
    thread.start()
    thread.join(timeout=3.0)

    os.close(r_fd)
    os.close(w_fd)

    assert len(select_rlists) > 0, "No select() calls were made — shim loop did not run"

    offending = [rlist for rlist in select_rlists if r_fd in rlist]
    assert not offending, (
        f"stdin fd {r_fd!r} appeared in select() rlist when isatty()=False. "
        f"Implementation must gate stdin inclusion on isatty(). "
        f"Offending rlists: {offending}"
    )


def test_stdin_source_read_never_called_during_run_loop_when_not_isatty(tmp_path):
    """stdin_source.read() must not be called from _run_loop when isatty() is False.

    Verifies that the isatty() guard prevents forward_stdin_once() from being
    invoked from within the run loop when stdin is not a TTY.
    """
    from atdd.coach.shim import PersonaShim

    r_fd, w_fd = os.pipe()
    os.write(w_fd, b"should-not-be-read\n")

    fake_stdin = _FakeStdinNonTTY(r_fd)

    shim = PersonaShim(
        agent_id="e005-unit-002-noread",
        spawn_command=["python3", "-c", "import time; time.sleep(0.4)"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: None,
        stdin_source=fake_stdin,
    )

    thread = threading.Thread(target=shim.run, kwargs={"timeout": 0.6}, daemon=True)
    thread.start()
    thread.join(timeout=3.0)

    os.close(r_fd)
    os.close(w_fd)

    assert fake_stdin.read_count == 0, (
        f"stdin_source.read() was called {fake_stdin.read_count} time(s) from _run_loop "
        f"even though isatty()=False. The TTY guard is missing or incorrect."
    )


def test_cli_return_still_delivered_when_stdin_not_isatty(tmp_path):
    """cli-return.jsonl corrections reach pty_write_sink regardless of stdin TTY status.

    Regression guard: adding stdin-forwarding must not break the existing
    cli-return delivery path when running in non-TTY (CI) mode.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e005-unit-002-cli-return"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    correction_text = "apply canonical layout now\n"
    _write_cli_return(cli_return_path, correction_text)

    pty_writes: list[bytes] = []
    r_fd, w_fd = os.pipe()

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["python3", "-c", "import time; time.sleep(0.6)"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: pty_writes.append(data),
        stdin_source=_FakeStdinNonTTY(r_fd),
    )

    thread = threading.Thread(target=shim.run, kwargs={"timeout": 0.8}, daemon=True)
    thread.start()
    thread.join(timeout=3.0)

    os.close(r_fd)
    os.close(w_fd)

    delivered = b"".join(pty_writes)
    assert b"apply canonical layout now" in delivered, (
        f"cli-return correction was not delivered to pty_write_sink when stdin is "
        f"non-TTY. Existing poll_once() path must be unaffected. Got: {delivered!r}"
    )


def test_shim_does_not_crash_when_stdin_not_isatty(tmp_path):
    """PersonaShim runs to completion without exception when isatty()=False.

    Verifies that the conditional stdin path does not introduce any crashes
    or unhandled exceptions in CI/non-interactive invocations.
    """
    from atdd.coach.shim import PersonaShim

    r_fd, w_fd = os.pipe()

    shim = PersonaShim(
        agent_id="e005-unit-002-nocrash",
        spawn_command=["python3", "-c", "import sys; sys.exit(0)"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: None,
        stdin_source=_FakeStdinNonTTY(r_fd),
    )

    exc_holder: list[BaseException] = []

    def run_shim():
        try:
            shim.run(timeout=3.0)
        except Exception as exc:
            exc_holder.append(exc)

    thread = threading.Thread(target=run_shim, daemon=True)
    thread.start()
    thread.join(timeout=5.0)

    os.close(r_fd)
    os.close(w_fd)

    assert not exc_holder, (
        f"PersonaShim raised an exception when stdin_source.isatty()=False: "
        f"{exc_holder[0]!r}"
    )
