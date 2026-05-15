# URN: component:integration-hardening:coach-cold-start-wiring:test_coach_stale_done_json_baseline:backend:tests
# Runtime: python
# Purpose: #711 (WMBT C005) — RuntimeWatcher baseline so a stale done.json does not advance the coach.

"""Regression tests for #711 — stale-`done.json` premature-advance guard.

#708's `agent_done` advance path advanced the coach phase on *any* `done.json`
in the persona's worktree runtime — including a leftover one from a prior run
(a fresh `RuntimeWatcher` starts with an empty `_snapshots`, so its first scan
treats a pre-existing file as new). Lived regression:
`coach-run-690-cb0a26c9` advanced PLANNED→RED in 9 s on a stale `done.json`.

Fix (WMBT C005): the coach calls `RuntimeWatcher.baseline()` at dispatch time —
every pre-existing runtime file is recorded as already-seen, so only files
written *after* the baseline are emitted.

Covers `acc:integration-hardening:C005-INTEGRATION-001` (stale done.json does
not advance) and `…-002` (the current persona's fresh done.json advances once).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.commands.event_queue import CoachEventQueue
from atdd.coach.commands.runtime_watcher import RuntimeWatcher

pytestmark = [pytest.mark.platform]


def _done(runtime: Path, agent_id: str, summary: str = "done") -> Path:
    d = runtime / "agents" / agent_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "done.json"
    p.write_text(json.dumps({"timestamp": "2026-05-15T00:00:00Z", "summary": summary}),
                 encoding="utf-8")
    return p


# --- C005-INTEGRATION-001: stale done.json does not advance ----------------


def test_baseline_suppresses_a_preexisting_done_json(tmp_path):
    """A done.json present BEFORE baseline() is not emitted on the first scan."""
    runtime = tmp_path / ".atdd" / "runtime"
    _done(runtime, "planner-711-stalerun")  # leftover from a prior run
    queue = CoachEventQueue(runtime_dir=runtime)
    watcher = RuntimeWatcher(runtime_dir=runtime, queue=queue)

    watcher.baseline()                       # dispatch-time baseline
    emitted = watcher.scan_once()            # first real scan

    assert emitted == 0, "stale done.json must not be emitted as new"
    assert queue.drain() == []


def test_without_baseline_a_preexisting_done_json_would_emit(tmp_path):
    """Control: absent baseline(), the first scan DOES emit it — proving the
    test above exercises the fix, not a no-op."""
    runtime = tmp_path / ".atdd" / "runtime"
    _done(runtime, "planner-711-stalerun")
    queue = CoachEventQueue(runtime_dir=runtime)
    watcher = RuntimeWatcher(runtime_dir=runtime, queue=queue)

    emitted = watcher.scan_once()            # no baseline()

    assert emitted == 1
    assert queue.drain()[0]["event_type"] == "agent_done"


# --- C005-INTEGRATION-002: the current persona's fresh done.json advances ---


def test_fresh_done_json_after_baseline_emits_exactly_once(tmp_path):
    """With a stale done.json baselined, the freshly-dispatched persona's own
    done.json still emits exactly one agent_done; a second scan emits nothing."""
    runtime = tmp_path / ".atdd" / "runtime"
    _done(runtime, "planner-711-priorrun")   # stale — baselined away
    queue = CoachEventQueue(runtime_dir=runtime)
    watcher = RuntimeWatcher(runtime_dir=runtime, queue=queue)
    watcher.baseline()

    # the current run's persona writes its OWN done.json after dispatch
    _done(runtime, "planner-711-currentrun")
    first = watcher.scan_once()
    second = watcher.scan_once()

    assert first == 1
    assert second == 0
    events = queue.drain()
    assert len(events) == 1
    assert events[0]["event_type"] == "agent_done"
    assert events[0]["agent_id"] == "planner-711-currentrun"


def test_baseline_is_safe_when_runtime_dir_absent(tmp_path):
    """baseline() on a runtime dir with no agents/ subdir is a no-op."""
    runtime = tmp_path / ".atdd" / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime)
    watcher = RuntimeWatcher(runtime_dir=runtime, queue=queue)
    watcher.baseline()  # must not raise
    assert watcher.scan_once() == 0
