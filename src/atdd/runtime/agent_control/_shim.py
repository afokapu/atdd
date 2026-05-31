"""Pty-owning shim engine: spawns the agent CLI as a child process in a pty it
owns, tees output to output.log, polls cli-return.jsonl, writes correction bytes
(prompt + submit sentinel) to the agent's pty stdin, forwards operator stdin, and
delivers an INTERRUPT to the wrapped process.

Architectural principle (#824):
  multiplexer for process and pixels; files-on-disk for semantics.

  The shim owns the pty. The controller (or observer) writes corrections to
  cli-return.jsonl. The shim drains cli-return.jsonl and writes bytes to the pty
  master fd, ALWAYS terminating each correction with the submit sentinel so the
  prompt is both injected AND submitted (closes #872).

This module was extracted from ``atdd.coach.shim.persona_shim`` into the
``atdd.runtime.agent_control`` layer (Child 6, docs/coach-decomposition.md §13.6).
It imports stdlib only — no ``atdd.coach`` / ``atdd.train`` / ``atdd.integrations``
/ ``atdd.runtime.multiplexer`` (§3.3).
"""
from __future__ import annotations

import json
import logging
import os
import pty
import select
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, IO, Optional, Sequence

_logger = logging.getLogger(__name__)

_UNSET = object()  # sentinel for unset submit_sentinel kwarg


class PersonaShim:
    """Pty-owning wrapper for an agent CLI process.

    Parameters
    ----------
    agent_id:
        Runtime agent identifier. Used to locate
        ``<runtime_dir>/agents/<id>/`` directory.
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
    stdout_sink:
        Optional test-only callable. When provided, bytes that would be
        written to ``sys.stdout.buffer`` are passed to this sink instead.
    submit_sentinel:
        Bytes appended to every delivered correction so the prompt is
        submitted. Resolution order: constructor kwarg > env var
        (``ATDD_SHIM_SUBMIT_SENTINEL``) > ``b"\\n"``.
    """

    def __init__(
        self,
        *,
        agent_id: str,
        spawn_command: Sequence[str],
        runtime_dir: Optional[Path],
        env_overrides: Optional[dict[str, str]] = None,
        pty_write_sink: Optional[Callable[[bytes], None]] = None,
        stdin_source: Optional[object] = None,
        stdout_sink: Optional[Callable[[bytes], None]] = None,
        submit_sentinel: object = _UNSET,
    ) -> None:
        self.agent_id = agent_id
        self.spawn_command = list(spawn_command)
        self.runtime_dir = runtime_dir
        self.env_overrides: dict[str, str] = env_overrides or {}
        self._pty_write_sink = pty_write_sink
        self._stdin_source = stdin_source
        self._stdout_sink = stdout_sink

        # E007: submit sentinel — constructor kwarg > env var > b"\n" (line terminator)
        if submit_sentinel is not _UNSET:
            self._submit_sentinel: bytes = submit_sentinel  # type: ignore[assignment]
        else:
            env_val = os.environ.get("ATDD_SHIM_SUBMIT_SENTINEL", "")
            self._submit_sentinel = env_val.encode("utf-8") if env_val else b"\n"

        # Per-agent runtime dir: <runtime_dir>/agents/<agent_id>/
        if runtime_dir is not None:
            self._agent_dir = Path(runtime_dir) / "agents" / agent_id
            self._agent_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._agent_dir = None  # type: ignore[assignment]

        # State
        self._cli_return_offset: int = 0
        self._master_fd: Optional[int] = None
        self._proc: Optional[subprocess.Popen] = None

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
            # Shape A fix (#854): merge env_overrides on top of os.environ so
            # env vars like ATDD_AGENT_ID reach the process via the env= kwarg
            # rather than through shell-style KEY=value argv[0] prefixes (which
            # fail without shell=True in Popen).
            popen_env = {**os.environ, **self.env_overrides} if self.env_overrides else None
            proc = subprocess.Popen(
                self.spawn_command,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                env=popen_env,
            )
            self._proc = proc
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
            except OSError as e:
                _logger.debug(
                    "master_fd close skipped",
                    extra={"master_fd": master_fd, "error": str(e)},
                )
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
            data = sys.stdin.buffer.read(1024)
        else:
            data = source.read(1024)
        if data:
            self._write_to_pty(data)

    # ------------------------------------------------------------------
    # Lifecycle / signalling (Child 6 — closes #871)
    # ------------------------------------------------------------------

    def is_alive(self) -> bool:
        """True while the wrapped child process is running."""
        return self._proc is not None and self._proc.poll() is None

    def send_interrupt(self) -> None:
        """Deliver an INTERRUPT to the wrapped agent (closes #871).

        Sends SIGINT to the child process group AND writes the canonical ETX
        (Ctrl-C) byte to the pty so a foreground TUI reading the pty in
        canonical mode is interrupted regardless of process-group nuances.
        """
        proc = self._proc
        # Ctrl-C over the pty (terminal-level interrupt for the foreground app).
        try:
            self._write_to_pty(b"\x03")
        except OSError as exc:
            _logger.debug("pty interrupt write skipped", extra={"error": str(exc)})
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.send_signal(signal.SIGINT)
        except (OSError, ProcessLookupError) as exc:  # pragma: no cover - race on exit
            _logger.debug(
                "send_interrupt SIGINT skipped", extra={"agent_id": self.agent_id, "error": str(exc)}
            )

    def terminate(self, *, grace_s: float = 2.0) -> None:
        """Terminate the wrapped agent: SIGTERM then SIGKILL after a grace."""
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError as exc:  # pragma: no cover - race on exit
                _logger.debug("kill skipped", extra={"error": str(exc)})
        except OSError as exc:  # pragma: no cover - race on exit
            _logger.debug("terminate skipped", extra={"error": str(exc)})

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
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        poll_interval = 0.1

        # E006: wait-for-ready gate
        ready_marker = os.environ.get("ATDD_SHIM_READY_MARKER", "❯").encode("utf-8")
        bootstrap_delay = float(os.environ.get("ATDD_SHIM_BOOTSTRAP_DELAY_S", "3.0"))
        spawn_time = time.monotonic()
        ready_gate_open = False
        output_log_path = (self._agent_dir / "output.log") if self._agent_dir else None
        # Include stdin fd in select only when stdin is a real TTY (E005).
        stdin_source = self._stdin_source or sys.stdin.buffer
        try:
            stdin_is_tty = hasattr(stdin_source, "isatty") and stdin_source.isatty()
            stdin_fd = stdin_source.fileno() if stdin_is_tty else None
        except Exception:
            stdin_fd = None

        while proc.poll() is None:
            if deadline is not None and time.monotonic() > deadline:
                proc.terminate()
                proc.wait(timeout=2.0)
                break

            # Build select watch list: always watch pty output; add stdin when TTY.
            watch = [master_fd]
            if stdin_fd is not None:
                watch.append(stdin_fd)

            rlist, _, _ = select.select(watch, [], [], poll_interval)

            # Forward operator keystrokes to the pty when stdin becomes readable.
            if stdin_fd is not None and stdin_fd in rlist:
                self.forward_stdin_once()

            # Read pty output (non-blocking)
            if master_fd in rlist:
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        if log_fh is not None:
                            log_fh.write(data)
                            log_fh.flush()
                        self._write_to_stdout(data)
                except OSError:
                    break

            # E006: open the gate when ready-marker seen or bootstrap delay elapsed
            if not ready_gate_open:
                elapsed = time.monotonic() - spawn_time
                if elapsed >= bootstrap_delay:
                    ready_gate_open = True
                elif output_log_path is not None and output_log_path.exists():
                    try:
                        content = output_log_path.read_bytes()
                        if ready_marker in content:
                            ready_gate_open = True
                    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
                        pass

            # Drain cli-return inbox (only after gate opens)
            if ready_gate_open:
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
                self._write_to_stdout(data)
        except OSError as e:
            _logger.debug("pty drain stopped on process exit", extra={"error": str(e)})

    def _process_cli_return_line(self, line: str) -> None:
        """Parse a single cli-return.jsonl line and deliver to pty."""
        if not line:
            return
        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            _logger.warning(
                "skipping invalid JSON in cli-return.jsonl",
                extra={
                    "agent_id": self.agent_id,
                    "offset": self._cli_return_offset,
                    "line_preview": line[:80],
                    "error": str(e),
                },
            )
            return

        correction_text = record.get("correction_text")
        if not correction_text or not isinstance(correction_text, str):
            _logger.warning(
                "skipping cli-return record missing correction_text",
                extra={"agent_id": self.agent_id, "record_keys": list(record.keys())},
            )
            return

        # Inject AND submit: the submit sentinel is ALWAYS appended (closes #872).
        payload = correction_text.encode("utf-8") + self._submit_sentinel
        self._write_to_pty(payload)

    def _write_to_pty(self, data: bytes) -> None:
        """Write bytes to the pty master fd (or the test sink)."""
        if self._pty_write_sink is not None:
            self._pty_write_sink(data)
        elif self._master_fd is not None:
            try:
                os.write(self._master_fd, data)
            except OSError as e:
                _logger.debug("pty write failed", extra={"agent_id": self.agent_id, "error": str(e)})

    def _write_to_stdout(self, data: bytes) -> None:
        """Forward pty output bytes to operator-visible stdout."""
        if self._stdout_sink is not None:
            try:
                self._stdout_sink(data)
            except OSError as e:
                _logger.warning(
                    "stdout forward failed",
                    extra={"agent_id": self.agent_id, "error": str(e)},
                )
            return
        try:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        except OSError as e:
            _logger.warning(
                "stdout forward failed",
                extra={"agent_id": self.agent_id, "error": str(e)},
            )
