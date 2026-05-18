# URN: test:observe-and-correct:observer-runtime-and-rules:P001-UNIT-010-teardown-fixture-reaps-observer-procs
# Acceptance: acc:observe-and-correct:P001-UNIT-010-teardown-fixture-reaps-observer-procs
# WMBT: wmbt:observe-and-correct:P001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""P001-UNIT-010 — conftest.py teardown fixture reaps spawned observer processes.

The ``observer_proc`` fixture from conftest.py must:
- Provide a ``spawn()`` factory that records subprocesses.
- Terminate all registered processes during teardown (SIGTERM → SIGKILL).
- Leave no process alive after teardown returns.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_observer_proc_fixture_exists(observer_proc):
    """The conftest.py must expose an observer_proc fixture."""
    assert observer_proc is not None
    assert hasattr(observer_proc, "spawn"), (
        "observer_proc fixture must have a .spawn() method"
    )


def test_observer_proc_spawn_returns_popen(observer_proc, tmp_path):
    """observer_proc.spawn() returns a live subprocess.Popen object."""
    # Spawn a trivial long-running process (not atdd, just to test the factory)
    proc = observer_proc.spawn(
        sys.executable, "-c", "import time; time.sleep(60)",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert isinstance(proc, subprocess.Popen)
    assert proc.poll() is None, "Spawned process should still be alive"
    # teardown (via fixture) will kill it — no explicit cleanup here


def test_observer_proc_teardown_kills_running_process(tmp_path):
    """After fixture teardown, registered processes are dead.

    We simulate teardown by calling factory.teardown() directly.
    """
    from src.atdd.coach.commands.tests.conftest import _ObserverProcFactory

    factory = _ObserverProcFactory()
    proc = factory.spawn(
        sys.executable, "-c", "import time; time.sleep(60)",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    assert proc.poll() is None, "Process must be alive before teardown"

    factory.teardown()

    # Poll a moment after teardown
    time.sleep(0.1)
    assert proc.poll() is not None, (
        "Process must be dead after fixture teardown — "
        "_ObserverProcFactory.teardown() must terminate spawned procs"
    )


def test_observer_proc_teardown_is_idempotent(tmp_path):
    """factory.teardown() can be called multiple times without error."""
    from src.atdd.coach.commands.tests.conftest import _ObserverProcFactory

    factory = _ObserverProcFactory()
    proc = factory.spawn(
        sys.executable, "-c", "import time; time.sleep(60)",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    factory.teardown()
    factory.teardown()  # second call must not raise

    time.sleep(0.1)
    assert proc.poll() is not None
