"""Hermetic fakes + a real-registry builder for coach-runtime tests.

The manager registry and the jsonl reader/cursor are REAL (plain file I/O over
tmp_path) — only the process/clock seams (spawn, liveness, signal, sleep, stop)
are faked, so the tests exercise the production cursor + pidfile code paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional


class RecordingSpawner:
    """Captures the surface launch (argv + name + durable log_path) and returns a
    scripted daemon cmux workspace ref."""

    def __init__(self, daemon_workspace: str = "workspace:42") -> None:
        self.calls: List[List[str]] = []
        self.names: List[str] = []
        self.log_paths: List[Optional[str]] = []
        self._daemon_workspace = daemon_workspace

    def spawn(
        self, argv: List[str], *, name: str, log_path: Optional[str] = None
    ) -> str:
        self.calls.append(list(argv))
        self.names.append(name)
        self.log_paths.append(log_path)
        return self._daemon_workspace


class FakeLiveness:
    """Liveness probe with an explicit set of live daemon workspace refs."""

    def __init__(self, alive: Optional[set] = None) -> None:
        self.alive = set(alive or ())

    def is_alive(self, daemon_workspace: str) -> bool:
        return daemon_workspace in self.alive


class RecordingCloser:
    """Records the daemon workspace refs asked to close (cmux close-workspace)."""

    def __init__(self) -> None:
        self.calls: List[str] = []

    def close(self, daemon_workspace: str) -> None:
        self.calls.append(daemon_workspace)


class StubGate:
    def __init__(self, rc: int = 0) -> None:
        self.rc = rc
        self.calls = 0

    def run(self) -> int:
        self.calls += 1
        return self.rc


class ImmediateSleeper:
    def __init__(self) -> None:
        self.calls = 0

    def sleep(self, seconds: float) -> None:
        self.calls += 1


class CountingStop:
    """is_set() returns False for the first `false_polls` calls, then True."""

    def __init__(self, false_polls: int = 1) -> None:
        self._remaining = false_polls

    def is_set(self) -> bool:
        if self._remaining > 0:
            self._remaining -= 1
            return False
        return True


class NeverStop:
    def is_set(self) -> bool:
        return False


def fake_argv(**kwargs) -> List[str]:
    """A daemon_argv builder that records the launch intent without a process."""
    return [
        "feed-daemon",
        "--workspace",
        kwargs["workspace_id"],
        "--lock",
        kwargs["lock_path"],
        "--escalations",
        kwargs["escalations_path"],
        "--verdicts",
        kwargs["verdicts_path"],
    ]
