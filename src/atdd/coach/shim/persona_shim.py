"""Persona-shim: pty-owning wrapper that spawns the agent CLI as a child
process, tees output to output.log, polls cli-return.jsonl, and writes
correction bytes to the agent's pty stdin.

Architectural principle (#824):
  multiplexer for process and pixels; files-on-disk for semantics.

  The shim owns the pty. The observer writes corrections to cli-return.jsonl.
  The shim drains cli-return.jsonl and writes bytes to the pty master fd.
"""
from __future__ import annotations

import json
import os
import pty
import select
import subprocess
import threading
from pathlib import Path
from typing import Callable, IO, List, Optional, Sequence


class PersonaShim:
    """Pty-owning wrapper for an agent CLI process.

    Parameters
    ----------
    agent_id:
        Runtime agent identifier. Used to locate
        ``.atdd/runtime/agents/<id>/`` directory.
    spawn_command:
        argv list for the agent CLI (e.g. ``["claude", "--dangerously-skip-permissions"]``).
    runtime_dir:
        Root runtime directory (default: ``.atdd/runtime``). May be None
        for pure unit tests that never call ``run()``.
    pty_write_sink:
        Optional test-only callable. When provided, bytes that would be
        written to the pty master fd are passed to this sink instead.
        Allows unit tests to capture deliveries without a real pty.
    stdin_source:
        Optional test-only object with a ``read(n) -> bytes`` method.
        When provided, operator-forwarding reads from this instead of
        ``sys.stdin.buffer``.
    """

    def __init__(
        self,
        *,
        agent_id: str,
        spawn_command: Sequence[str],
        runtime_dir: Optional[Path],
        pty_write_sink: Optional[Callable[[bytes], None]] = None,
        stdin_source: Optional[object] = None,
    ) -> None:
        self.agent_id = agent_id
        self.spawn_command = list(spawn_command)
        self.runtime_dir = runtime_dir
        self._pty_write_sink = pty_write_sink
        self._stdin_source = stdin_source

        # Per-agent runtime dir: <runtime_dir>/agents/<agent_id>/
        if runtime_dir is not None:
            self._agent_dir = Path(runtime_dir) / "agents" / agent_id
            self._agent_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._agent_dir = None  # type: ignore[assignment]

        # State
        self._cli_return_offset: int = 0
        self._master_fd: Optional[int] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, timeout: Optional[float] = None) -> int:
        """Spawn the agent CLI in a pty, tee output to output.log, and
        poll cli-return.jsonl until the child exits.

        Returns the child process exit code.
        """
        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd

        try:
            proc = subprocess.Popen(
                self.spawn_command,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
            os.close(slave_fd)

            output_log = self._agent_dir / "output.log" if self._agent_dir else None
            log_fh = open(output_log, "ab") if output_log else None

            try:
                self._run_loop(master_fd, proc, log_fh, timeout)
            finally:
                if log_fh is not None:
                    log_fh.close()

            return proc.returncode if proc.returncode is not None else 0
        finally:
            try:
                os.close(master_fd)
            except OSError:
                pass
            self._master_fd = None

    def poll_once(self) -> None:
        """Drain one batch of unconsumed cli-return.jsonl entries and
        deliver each correction_text to the pty (or pty_write_sink).

        Designed for unit tests and the shim's internal poll loop.
        """
        if self._agent_dir is None:
            return
        cli_return_path = self._agent_dir / "cli-return.jsonl"
        if not cli_return_path.exists():
            return

        with cli_return_path.open("r", encoding="utf-8") as fh:
            fh.seek(self._cli_return_offset)
            while True:
                line = fh.readline()
                if not line:
                    break
                self._cli_return_offset = fh.tell()
                self._process_cli_return_line(line.rstrip("\n"))

    def forward_stdin_once(self) -> None:
        """Read one chunk from stdin_source and write to the pty.

        Designed for unit tests that simulate operator keystrokes.
        """
        source = self._stdin_source
        if source is None:
            import sys
            data = sys.stdin.buffer.read(1024)
        else:
            data = source.read(1024)
        if data:
            self._write_to_pty(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_loop(
        self,
        master_fd: int,
        proc: subprocess.Popen,
        log_fh: Optional[IO[bytes]],
        timeout: Optional[float],
    ) -> None:
        """Main event loop: tee pty output + poll cli-return + forward stdin."""
        import sys
        import time

        deadline = (time.monotonic() + timeout) if timeout is not None else None
        poll_interval = 0.1

        while proc.poll() is None:
            if deadline is not None and time.monotonic() > deadline:
                proc.terminate()
                proc.wait(timeout=2.0)
                break

            # Read pty output (non-blocking)
            rlist, _, _ = select.select([master_fd], [], [], poll_interval)
            if rlist:
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        if log_fh is not None:
                            log_fh.write(data)
                            log_fh.flush()
                except OSError:
                    break

            # Drain cli-return inbox
            self.poll_once()

        # Drain remaining output after process exits
        try:
            while True:
                rlist, _, _ = select.select([master_fd], [], [], 0.0)
                if not rlist:
                    break
                data = os.read(master_fd, 4096)
                if not data:
                    break
                if log_fh is not None:
                    log_fh.write(data)
                    log_fh.flush()
        except OSError:
            pass

    def _process_cli_return_line(self, line: str) -> None:
        """Parse a single cli-return.jsonl line and deliver to pty."""
        if not line:
            return
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            import sys
            print(
                f"[shim] WARNING: skipping invalid JSON in cli-return.jsonl "
                f"at offset {self._cli_return_offset}: {line[:80]!r}",
                file=sys.stderr,
            )
            return

        correction_text = record.get("correction_text")
        if not correction_text or not isinstance(correction_text, str):
            import sys
            print(
                f"[shim] WARNING: skipping cli-return record missing 'correction_text': "
                f"{list(record.keys())}",
                file=sys.stderr,
            )
            return

        self._write_to_pty(correction_text.encode("utf-8"))

    def _write_to_pty(self, data: bytes) -> None:
        """Write bytes to the pty master fd (or the test sink)."""
        if self._pty_write_sink is not None:
            self._pty_write_sink(data)
        elif self._master_fd is not None:
            try:
                os.write(self._master_fd, data)
            except OSError:
                pass
