# URN: test:observe-and-correct:observer-runtime-and-rules:E002-UNIT-001-coach-starts-one-observer
# Acceptance: acc:observe-and-correct:E002-UNIT-001-coach-starts-one-observer
# WMBT: wmbt:observe-and-correct:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E002-UNIT-001 — coach._execute_cold_start starts exactly one MultiAgentObserver
regardless of how many workers are driven.

RED: no MultiAgentObserver class exists and coach does not start any
coach-level observer — multiple per-worker observers are spawned instead.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMultiAgentObserver:
    """Records start()/stop() calls."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.start_calls: int = 0
        self.stop_calls: int = 0

    def start(self) -> "_FakeMultiAgentObserver":
        self.start_calls += 1
        return self

    def stop(self) -> None:
        self.stop_calls += 1


def test_execute_cold_start_starts_exactly_one_observer(tmp_path, monkeypatch):
    """_execute_cold_start starts exactly one MultiAgentObserver; stop() called once."""
    from atdd.coach.commands.coach import Config, _execute_cold_start, initialize_state_machine
    from atdd.coach.handlers.state_machine import Phase

    # Patch out spawn so the cold-start drive is fast
    monkeypatch.setattr(
        "atdd.coach.handlers.spawn.handle",
        lambda ctx, t: __import__("atdd.coach.handlers.state_machine", fromlist=["HandlerResult"]).HandlerResult.HANDLED,
    )
    monkeypatch.setattr(
        "atdd.coach.handlers.two_phase_commit.handle",
        lambda ctx, t: __import__("atdd.coach.handlers.state_machine", fromlist=["HandlerResult"]).HandlerResult.NOOP,
    )

    observer_instances: list[_FakeMultiAgentObserver] = []

    def _fake_observer_factory(runtime_root: Path, **kwargs: Any) -> _FakeMultiAgentObserver:
        obs = _FakeMultiAgentObserver(runtime_root, **kwargs)
        observer_instances.append(obs)
        return obs

    from atdd.coach.commands import observer as obs_mod
    # Inject the factory — E002-UNIT-001 requires MultiAgentObserver exists in observer module
    monkeypatch.setattr(obs_mod, "MultiAgentObserver", _fake_observer_factory)

    cfg = Config(
        issue_numbers=[101, 102, 103],
        multiplexer_mode="workspace",
        dry_run=False,
    )
    machines = [initialize_state_machine(n) for n in [101, 102, 103]]
    runtime_dir = tmp_path / ".atdd" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    _execute_cold_start(
        cfg,
        machines,
        runtime_dir,
        _max_loop_events=0,
    )

    assert len(observer_instances) == 1, (
        f"Expected exactly 1 MultiAgentObserver started, got {len(observer_instances)}"
    )
    obs = observer_instances[0]
    assert obs.start_calls == 1, (
        f"Expected observer.start() called once, got {obs.start_calls}"
    )
    assert obs.stop_calls == 1, (
        f"Expected observer.stop() called once after waves, got {obs.stop_calls}"
    )
