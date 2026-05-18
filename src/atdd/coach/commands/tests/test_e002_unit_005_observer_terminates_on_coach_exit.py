# URN: test:observe-and-correct:observer-runtime-and-rules:E002-UNIT-005-observer-terminates-on-coach-exit
# Acceptance: acc:observe-and-correct:E002-UNIT-005-observer-terminates-on-coach-exit
# WMBT: wmbt:observe-and-correct:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E002-UNIT-005 — MultiAgentObserver.stop() signals the thread and it
terminates within a reasonable timeout (3.0s).

RED: MultiAgentObserver does not exist yet.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_TERMINATE_TIMEOUT = 3.0


def test_observer_starts_background_thread(tmp_path):
    """start() launches a daemon thread named 'coach-observer'."""
    from atdd.coach.commands.observer import MultiAgentObserver

    obs = MultiAgentObserver(runtime_root=tmp_path, poll_interval=60.0)
    obs.start()
    try:
        assert obs._thread is not None, "Expected _thread to be set after start()"
        assert obs._thread.is_alive(), "Expected thread to be alive after start()"
        assert obs._thread.daemon, "Expected daemon=True so it doesn't block process exit"
    finally:
        obs.stop()


def test_observer_stop_terminates_thread_within_timeout(tmp_path):
    """stop() sets the stop event and the thread exits within 3.0s."""
    from atdd.coach.commands.observer import MultiAgentObserver

    obs = MultiAgentObserver(runtime_root=tmp_path, poll_interval=60.0)
    obs.start()

    stop_start = time.monotonic()
    obs.stop()
    elapsed = time.monotonic() - stop_start

    assert not obs._stop.is_set() or obs._stop.is_set(), "stop event should be set"
    assert obs._stop.is_set(), "Expected _stop event to be set after stop()"

    if obs._thread is not None:
        obs._thread.join(timeout=_TERMINATE_TIMEOUT)
        assert not obs._thread.is_alive(), (
            f"Observer thread still alive after {_TERMINATE_TIMEOUT}s — "
            f"observer does not terminate cleanly on stop()"
        )

    assert elapsed < _TERMINATE_TIMEOUT + 1.0, (
        f"stop() took {elapsed:.1f}s; expected < {_TERMINATE_TIMEOUT + 1.0}s"
    )


def test_observer_stop_is_idempotent(tmp_path):
    """stop() can be called multiple times without error."""
    from atdd.coach.commands.observer import MultiAgentObserver

    obs = MultiAgentObserver(runtime_root=tmp_path, poll_interval=60.0)
    obs.start()
    obs.stop()
    obs.stop()  # second call must not raise
