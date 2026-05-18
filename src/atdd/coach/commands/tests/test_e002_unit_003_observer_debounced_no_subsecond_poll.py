# URN: test:observe-and-correct:observer-runtime-and-rules:E002-UNIT-003-observer-debounced-no-subsecond-poll
# Acceptance: acc:observe-and-correct:E002-UNIT-003-observer-debounced-no-subsecond-poll
# WMBT: wmbt:observe-and-correct:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E002-UNIT-003 — MultiAgentObserver poll_interval >= 1.0s by default;
sub-second values are clamped to the minimum.

RED: MultiAgentObserver does not exist yet.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]

_MIN_INTERVAL = 1.0


def test_default_poll_interval_is_not_subsecond(tmp_path):
    """Default MultiAgentObserver poll_interval >= 1.0s."""
    from atdd.coach.commands.observer import MultiAgentObserver

    obs = MultiAgentObserver(runtime_root=tmp_path)
    assert obs.poll_interval >= _MIN_INTERVAL, (
        f"Default poll_interval {obs.poll_interval} is sub-second — "
        f"MultiAgentObserver must not busy-wait (minimum {_MIN_INTERVAL}s)"
    )


def test_subsecond_poll_interval_is_clamped(tmp_path):
    """Passing poll_interval < 1.0 is silently clamped to the minimum."""
    from atdd.coach.commands.observer import MultiAgentObserver, MULTI_OBSERVER_MIN_INTERVAL

    obs = MultiAgentObserver(runtime_root=tmp_path, poll_interval=0.01)
    assert obs.poll_interval >= MULTI_OBSERVER_MIN_INTERVAL, (
        f"poll_interval 0.01 was not clamped: got {obs.poll_interval}"
    )


def test_min_interval_constant_is_exported(tmp_path):
    """MULTI_OBSERVER_MIN_INTERVAL is a public constant >= 1.0."""
    from atdd.coach.commands.observer import MULTI_OBSERVER_MIN_INTERVAL

    assert MULTI_OBSERVER_MIN_INTERVAL >= _MIN_INTERVAL, (
        f"MULTI_OBSERVER_MIN_INTERVAL={MULTI_OBSERVER_MIN_INTERVAL} is < {_MIN_INTERVAL}"
    )
