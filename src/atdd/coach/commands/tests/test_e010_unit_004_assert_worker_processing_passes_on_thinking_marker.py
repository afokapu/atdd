# URN: test:spawn-agents:worker-launch-prompt-readiness-gate:E010-UNIT-004-assert-worker-processing-passes-on-thinking-marker
# Acceptance: acc:spawn-agents:E010-UNIT-004-assert-worker-processing-passes-on-thinking-marker
# WMBT: wmbt:spawn-agents:E010
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E010-UNIT-004 — _assert_worker_processing returns without raising when the
session jsonl byte size grows (Claude appended ≥1 new message), and raises
WorkerReadinessTimeout when the file does not grow within the timeout (#797).

RED: _assert_worker_processing still uses capture_surface_text which no
production backend implements (the hasattr guard silently skips the assertion
on every real dispatch). These tests call the function with the new
project_key + claude_projects_dir interface — they will TypeError against
the old signature until the fix lands.
"""
from __future__ import annotations

import threading
import time

import pytest


def test_returns_when_jsonl_grows(tmp_path):
    """_assert_worker_processing returns when the session jsonl byte size grows."""
    from atdd.coach.commands.spawn import _assert_worker_processing

    project_key = "test-project-key"
    project_dir = tmp_path / project_key
    project_dir.mkdir()
    jsonl = project_dir / "session.jsonl"
    jsonl.write_text("{}\n")

    def _grow():
        time.sleep(0.02)
        with jsonl.open("a") as f:
            f.write("{}\n")

    threading.Thread(target=_grow, daemon=True).start()

    _assert_worker_processing(
        surface_ref="surface:6",
        project_key=project_key,
        claude_projects_dir=tmp_path,
        timeout_s=2.0,
        poll_interval_s=0.01,
    )


def test_raises_when_jsonl_never_grows(tmp_path):
    """WorkerReadinessTimeout when the jsonl is static (worker never processes)."""
    from atdd.coach.commands.spawn import (
        WorkerReadinessTimeout,
        _assert_worker_processing,
    )

    project_key = "frozen-project"
    project_dir = tmp_path / project_key
    project_dir.mkdir()
    jsonl = project_dir / "session.jsonl"
    jsonl.write_text("{}\n")

    with pytest.raises(WorkerReadinessTimeout, match=project_key):
        _assert_worker_processing(
            surface_ref="surface:3",
            project_key=project_key,
            claude_projects_dir=tmp_path,
            timeout_s=0.1,
            poll_interval_s=0.01,
        )


def test_raises_when_no_jsonl_found(tmp_path):
    """WorkerReadinessTimeout when the project dir has no jsonl file."""
    from atdd.coach.commands.spawn import (
        WorkerReadinessTimeout,
        _assert_worker_processing,
    )

    project_key = "empty-project"
    (tmp_path / project_key).mkdir()

    with pytest.raises(WorkerReadinessTimeout):
        _assert_worker_processing(
            surface_ref="surface:42",
            project_key=project_key,
            claude_projects_dir=tmp_path,
            timeout_s=0.1,
            poll_interval_s=0.01,
        )
