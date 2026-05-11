# URN: test:integration-hardening:coach-state-machine-and-runtime:E001-INTEGRATION-002-stale-warn-fires
# Acceptance: acc:integration-hardening:E001-INTEGRATION-002-stale-warn-fires
# WMBT: wmbt:drive-state-machine:M001
# Phase: RED
# Layer: integration
"""J5-INTEGRATION-002 — `atdd coach --stale-warn 1` emits an INFO escalation
after the configured number of minutes without events.

Uses an injected clock so tests run without real wall-clock delays.
The escalation appears on `--escalation-channel`; in unit scope the
channel is a list that the WatcherEventLoop appends to.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_stale_warn_emits_escalation_after_timeout(tmp_path):
    """After stale_warn_minutes of silence, WatcherEventLoop emits a
    process_silence-style escalation on the configured channel."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = initialize_state_machine(issue_number=587)

    escalations: list[dict] = []

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=1,
        escalation_channel="test-channel",
        _escalation_sink=escalations,
    )

    loop.check_stale(elapsed_minutes=1.5)

    assert len(escalations) == 1
    esc = escalations[0]
    assert esc.get("level") in ("INFO", "WARN", "WARNING")
    assert esc.get("channel") == "test-channel"


def test_stale_warn_does_not_fire_before_threshold(tmp_path):
    """No escalation is emitted if elapsed time is below stale_warn_minutes."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = initialize_state_machine(issue_number=587)

    escalations: list[dict] = []

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=5,
        escalation_channel="test-channel",
        _escalation_sink=escalations,
    )

    loop.check_stale(elapsed_minutes=0.5)

    assert len(escalations) == 0


def test_stale_warn_none_never_fires(tmp_path):
    """When stale_warn_minutes is None, no escalation is emitted regardless
    of elapsed time."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = initialize_state_machine(issue_number=587)

    escalations: list[dict] = []

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel="test-channel",
        _escalation_sink=escalations,
    )

    loop.check_stale(elapsed_minutes=999)

    assert len(escalations) == 0


def test_stale_warn_bounded_one_per_window(tmp_path):
    """Exactly one escalation per silence window — not one per check_stale call."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = initialize_state_machine(issue_number=587)

    escalations: list[dict] = []

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=1,
        escalation_channel="test-channel",
        _escalation_sink=escalations,
    )

    loop.check_stale(elapsed_minutes=2.0)
    loop.check_stale(elapsed_minutes=3.0)
    loop.check_stale(elapsed_minutes=4.0)

    assert len(escalations) == 1, "Must emit at most one escalation per silence window"


def test_parse_cli_includes_stale_warn_flag():
    """parse_cli() accepts --stale-warn and maps to stale_warn_minutes on Config."""
    from atdd.coach.commands.coach import parse_cli

    cfg = parse_cli(["587", "--stale-warn", "3"])
    assert cfg.stale_warn_minutes == 3


def test_parse_cli_stale_warn_defaults_to_none():
    """--stale-warn is optional; default is None (never fires)."""
    from atdd.coach.commands.coach import parse_cli

    cfg = parse_cli(["587"])
    assert cfg.stale_warn_minutes is None
