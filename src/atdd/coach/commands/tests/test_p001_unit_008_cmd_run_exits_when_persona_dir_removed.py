# URN: test:observe-and-correct:observer-runtime-and-rules:P001-UNIT-008-cmd-run-exits-when-persona-dir-removed
# Acceptance: acc:observe-and-correct:P001-UNIT-008-cmd-run-exits-when-persona-dir-removed
# WMBT: wmbt:observe-and-correct:P001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""P001-UNIT-008 — `cmd_run` self-exits when persona runtime dir removed.

The observer's `while True` loop must check whether the persona's agent dir
still exists on each iteration. When the dir is deleted, `cmd_run` must
return 0 without waiting for a kill signal.
"""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_EXIT_TIMEOUT = 3.0  # seconds: max allowed time from dir-delete to return


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


def test_cmd_run_accepts_idle_timeout_kwarg(tmp_path: Path):
    """cmd_run must accept `idle_timeout` as a keyword argument (signature check)."""
    from atdd.coach.commands import observer
    import inspect

    sig = inspect.signature(observer.cmd_run)
    assert "idle_timeout" in sig.parameters, (
        "cmd_run must accept idle_timeout keyword argument (issue #769)"
    )


def test_cmd_run_exits_when_persona_dir_removed(tmp_path: Path):
    """cmd_run returns 0 within _EXIT_TIMEOUT seconds of persona dir deletion."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_id = "planner-42-observer"
    # persona dir is derived by stripping '-observer'
    persona_id = "planner-42"
    persona_dir = runtime / "agents" / persona_id
    persona_dir.mkdir(parents=True)
    (persona_dir / "output.log").write_text("hello\n")

    result_box: list = []
    poll = 0.1
    t = _run_cmd_run_in_thread(
        agent_id=agent_id,
        runtime_dir=runtime,
        poll_interval=poll,
        result_box=result_box,
        idle_timeout=300.0,
    )

    # Give it a moment to start its loop
    time.sleep(poll * 3)
    assert result_box == [], "cmd_run should still be running before dir removal"

    # Delete the persona dir
    shutil.rmtree(persona_dir)

    # Wait for cmd_run to notice and return
    t.join(timeout=_EXIT_TIMEOUT)

    assert not t.is_alive(), (
        f"cmd_run still alive {_EXIT_TIMEOUT}s after persona dir was removed; "
        "add a self-exit guard (issue #769)"
    )
    assert result_box == [0], f"cmd_run must return 0 on self-exit, got {result_box}"


def test_cmd_run_exits_when_runtime_root_removed(tmp_path: Path):
    """cmd_run returns 0 when the entire runtime root is deleted."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_id = "worker-1-observer"
    persona_id = "worker-1"
    persona_dir = runtime / "agents" / persona_id
    persona_dir.mkdir(parents=True)
    (persona_dir / "output.log").write_text("data\n")

    result_box: list = []
    poll = 0.1
    t = _run_cmd_run_in_thread(
        agent_id=agent_id,
        runtime_dir=runtime,
        poll_interval=poll,
        result_box=result_box,
        idle_timeout=300.0,
    )

    time.sleep(poll * 3)
    assert result_box == [], "cmd_run should still be running"

    shutil.rmtree(tmp_path / ".atdd")

    t.join(timeout=_EXIT_TIMEOUT)
    assert not t.is_alive(), (
        f"cmd_run still alive {_EXIT_TIMEOUT}s after runtime root was removed"
    )
    assert result_box == [0]
