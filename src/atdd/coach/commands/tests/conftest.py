"""Shared fixtures for coach commands tests.

Provides :func:`observer_proc` — a factory fixture that spawns ``atdd
observer run`` subprocesses and guarantees teardown so tests leave zero
orphaned observer processes behind.

Also provides :func:`_reap_leaked_observers` — an autouse safeguard that
kills any remaining orphaned ``atdd observer run`` processes after each test,
covering processes spawned outside the ``observer_proc`` factory.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Iterator, List

import pytest


@pytest.fixture
def observer_proc() -> Iterator[_ObserverProcFactory]:
    """Yield a factory that spawns observer subprocesses and reaps them on teardown."""
    factory = _ObserverProcFactory()
    yield factory
    factory.teardown()


class _ObserverProcFactory:
    def __init__(self) -> None:
        self._procs: List[subprocess.Popen] = []

    def spawn(self, *args: str, **popen_kwargs) -> subprocess.Popen:
        """Spawn a subprocess and register it for teardown."""
        proc = subprocess.Popen(args, **popen_kwargs)
        self._procs.append(proc)
        return proc

    def teardown(self) -> None:
        for proc in self._procs:
            if proc.poll() is not None:
                continue
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        self._procs.clear()


@pytest.fixture(autouse=True)
def _default_legacy_spawn_transport(monkeypatch) -> Iterator[None]:
    """#978 flipped the spawn dispatch default to **cmux-native**. Most cmd_spawn
    tests in this directory were written against the legacy tui-scrape (paste +
    readiness probe) surface path, so we pin that path explicitly here via
    ``ATDD_CORRECTION_TRANSPORT=tui-scrape`` (an explicit override wins by
    precedence and is stable across the default flip).

    NOTE: pre-#978 this fixture set ``ATDD_USE_LEGACY_SPAWN=1`` to reach the same
    paste path, but that kill switch now routes to the **shim** (cli-return) —
    the soak fallback for cmux-native — so it can no longer stand in for
    tui-scrape. Tests targeting a specific transport set their own
    ``ATDD_CORRECTION_TRANSPORT`` (cli-return / cmux-native) or
    ``ATDD_USE_LEGACY_SPAWN`` and win by precedence."""
    if (
        "ATDD_USE_LEGACY_SPAWN" not in os.environ
        and "ATDD_CORRECTION_TRANSPORT" not in os.environ
    ):
        monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "tui-scrape")
    yield


@pytest.fixture(autouse=True)
def _reap_leaked_observers() -> Iterator[None]:
    """Autouse guard: kill any orphaned 'atdd observer run' processes after each test."""
    yield
    try:
        result = subprocess.run(
            ["pgrep", "-f", "atdd observer run"],
            capture_output=True,
            text=True,
            check=False,
        )
        for pid_str in result.stdout.splitlines():
            pid_str = pid_str.strip()
            if not pid_str:
                continue
            try:
                pid = int(pid_str)
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, ValueError, PermissionError):
                pass
    except FileNotFoundError:
        # pgrep not available on this platform; skip
        pass
