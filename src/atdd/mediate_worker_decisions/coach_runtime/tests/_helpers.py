"""Hermetic fakes + a real-registry builder for coach-runtime tests.

The manager registry and the jsonl reader/cursor are REAL (plain file I/O over
tmp_path) — only the process/clock seams (spawn, liveness, signal, sleep, stop)
are faked, so the tests exercise the production cursor + pidfile code paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional


class RecordingSpawner:
    """Captures spawn argv and hands back a scripted pid each call."""

    def __init__(self, pid: int = 4242) -> None:
        self.calls: List[List[str]] = []
        self._pid = pid

    def spawn(self, argv: List[str]) -> int:
        self.calls.append(list(argv))
        return self._pid


class FakeLiveness:
    """Liveness probe with an explicit live-pid set."""

    def __init__(self, alive: Optional[set] = None) -> None:
        self.alive = set(alive or ())

    def is_alive(self, pid: int) -> bool:
        return pid in self.alive


class RecordingSignaller:
    def __init__(self) -> None:
        self.calls: List[tuple] = []

    def signal(self, pid: int, sig: int) -> None:
        self.calls.append((pid, sig))


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
