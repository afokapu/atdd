# URN: test:spawn-agents:coach-spawn-step-by-step-verify-each-stage:E011-UNIT-006-assert-worker-processing-hard-raises
# Acceptance: acc:spawn-agents:E011-UNIT-006-assert-worker-processing-hard-raises
# WMBT: wmbt:spawn-agents:E011
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E011-UNIT-006 — _assert_worker_processing raises WorkerReadinessTimeout when the
session .jsonl byte size does not grow within the timeout.

GREEN: PR #797 rewrote _assert_worker_processing to use jsonl byte-size growth
instead of capture_pane_text. This test verifies the hard-raise behaviour using
the new jsonl-based interface (project_key + claude_projects_dir).
"""
from __future__ import annotations

import pytest


def test_assert_worker_processing_hard_raises_when_jsonl_does_not_grow(tmp_path):
    """WorkerReadinessTimeout raised when jsonl stays static (Claude never responded)."""
    from atdd.coach.commands.spawn import WorkerReadinessTimeout, _assert_worker_processing

    project_key = "fake-project-key"
    project_dir = tmp_path / project_key
    project_dir.mkdir()
    jsonl = project_dir / "session.jsonl"
    jsonl.write_text('{"type":"system"}\n')

    with pytest.raises(WorkerReadinessTimeout):
        _assert_worker_processing(
            surface_ref="surface:5",
            project_key=project_key,
            claude_projects_dir=tmp_path,
            timeout_s=0.1,
            poll_interval_s=0.01,
        )


def test_assert_worker_processing_passes_when_jsonl_grows(tmp_path):
    """No exception when a second thread / process appends to the jsonl."""
    import threading
    import time

    from atdd.coach.commands.spawn import _assert_worker_processing

    project_key = "growing-project"
    project_dir = tmp_path / project_key
    project_dir.mkdir()
    jsonl = project_dir / "session.jsonl"
    jsonl.write_text('{"type":"system"}\n')

    def _append_after_delay():
        time.sleep(0.05)
        with jsonl.open("a") as fh:
            fh.write('{"type":"assistant","content":"Hi"}\n')

    t = threading.Thread(target=_append_after_delay, daemon=True)
    t.start()

    _assert_worker_processing(
        surface_ref="surface:6",
        project_key=project_key,
        claude_projects_dir=tmp_path,
        timeout_s=2.0,
        poll_interval_s=0.01,
    )
    t.join(timeout=1.0)
