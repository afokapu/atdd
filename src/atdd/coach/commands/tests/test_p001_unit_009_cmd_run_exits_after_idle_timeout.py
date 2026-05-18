# URN: test:observe-and-correct:observer-runtime-and-rules:P001-UNIT-009-cmd-run-exits-after-idle-timeout
# Acceptance: acc:observe-and-correct:P001-UNIT-009-cmd-run-exits-after-idle-timeout
# WMBT: wmbt:observe-and-correct:P001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""P001-UNIT-009 — `cmd_run` self-exits after configurable idle timeout.

When `idle_timeout` seconds elapse with no change to the persona's
output.log, `cmd_run` must return 0 without receiving a signal.
A zero/negative idle_timeout disables the check (run indefinitely w.r.t.
this condition).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_MARGIN = 2.0  # seconds of slack beyond idle_timeout before we declare failure


def _run_cmd_run_in_thread(
    *,
    agent_id: str,
    runtime_dir: Path,
    poll_interval: float,
    result_box: list,
    **kwargs,
) -> threading.Thread:
    from atdd.coach.commands import observer

    def _target():
        rc = observer.cmd_run(
            agent_id=agent_id,
            runtime_dir=runtime_dir,
            rules_dir=None,
            poll_interval=poll_interval,
            **kwargs,
        )
        result_box.append(rc)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    return t


def test_cmd_run_exits_after_idle_timeout_no_log_activity(tmp_path: Path):
    """cmd_run returns 0 after idle_timeout seconds when persona log is static."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_id = "planner-99-observer"
    persona_id = "planner-99"
    persona_dir = runtime / "agents" / persona_id
    persona_dir.mkdir(parents=True)
    # Write an initial log line (static — will not change)
    log = persona_dir / "output.log"
    log.write_text("initial line\n")

    idle_timeout = 1.0
    poll = 0.1
    result_box: list = []

    t = _run_cmd_run_in_thread(
        agent_id=agent_id,
        runtime_dir=runtime,
        poll_interval=poll,
        result_box=result_box,
        idle_timeout=idle_timeout,
    )

    deadline = idle_timeout + _MARGIN
    t.join(timeout=deadline)

    assert not t.is_alive(), (
        f"cmd_run still alive {deadline:.1f}s after start with idle_timeout={idle_timeout}; "
        "cmd_run must exit after idle_timeout seconds (issue #769)"
    )
    assert result_box == [0], f"Expected return code 0 on idle exit, got {result_box}"


def test_cmd_run_idle_timer_resets_on_log_activity(tmp_path: Path):
    """Writing to output.log resets the idle timer; cmd_run keeps running."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_id = "coder-5-observer"
    persona_id = "coder-5"
    persona_dir = runtime / "agents" / persona_id
    persona_dir.mkdir(parents=True)
    log = persona_dir / "output.log"
    log.write_text("line one\n")

    idle_timeout = 1.0
    poll = 0.05
    result_box: list = []

    t = _run_cmd_run_in_thread(
        agent_id=agent_id,
        runtime_dir=runtime,
        poll_interval=poll,
        result_box=result_box,
        idle_timeout=idle_timeout,
    )

    # Write to the log midway through the first idle window — reset the timer
    time.sleep(idle_timeout * 0.5)
    with log.open("a") as f:
        f.write("new activity\n")

    # At this point the timer should have reset; the process must still be alive
    time.sleep(idle_timeout * 0.3)
    assert result_box == [], (
        "cmd_run must NOT exit yet — idle timer was reset by log write"
    )

    # After full idle_timeout from last write, it should exit
    time.sleep(idle_timeout + _MARGIN)
    t.join(timeout=0.2)

    assert not t.is_alive(), (
        "cmd_run should have exited after idle_timeout from last log write"
    )
    assert result_box == [0]


def test_cmd_run_zero_idle_timeout_never_triggers(tmp_path: Path):
    """idle_timeout=0 disables the idle check; cmd_run must NOT exit due to idleness."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_id = "reviewer-3-observer"
    persona_id = "reviewer-3"
    persona_dir = runtime / "agents" / persona_id
    persona_dir.mkdir(parents=True)
    (persona_dir / "output.log").write_text("x\n")

    poll = 0.05
    result_box: list = []

    t = _run_cmd_run_in_thread(
        agent_id=agent_id,
        runtime_dir=runtime,
        poll_interval=poll,
        result_box=result_box,
        idle_timeout=0,  # disabled
    )

    # Wait well past what would be an idle timeout
    time.sleep(0.5)
    assert result_box == [], (
        "cmd_run must not exit on idle when idle_timeout=0 (disabled)"
    )

    # Clean up: remove persona dir so cmd_run exits via path (a)
    import shutil
    shutil.rmtree(persona_dir)
    t.join(timeout=2.0)
