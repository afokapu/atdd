# URN: test:govern-lifecycle:split-spawn-and-final-purity-sweep:observer-singleton-i6
# Source of truth: docs/coach-decomposition.md §8, §9 (I-6), §13.10 (umbrella #887)
"""I-6 — single observer lifecycle. Only one ObserverSession may be active."""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.observer import ObserverAlreadyRunningError, ObserverSession


@pytest.fixture(autouse=True)
def _reset_singleton():
    ObserverSession._active = None
    yield
    ObserverSession._active = None


def test_second_start_is_rejected(tmp_path):
    first = ObserverSession(tmp_path).start()
    with pytest.raises(ObserverAlreadyRunningError):
        ObserverSession(tmp_path).start()
    first.stop()


def test_stop_releases_the_slot(tmp_path):
    ObserverSession(tmp_path).start().stop()
    # After release a fresh session may start.
    second = ObserverSession(tmp_path).start()
    assert ObserverSession._active is second
    second.stop()


def test_context_manager_is_singleton_scoped(tmp_path):
    with ObserverSession(tmp_path):
        with pytest.raises(ObserverAlreadyRunningError):
            ObserverSession(tmp_path).start()
    # Exiting the context frees the slot.
    assert ObserverSession._active is None
