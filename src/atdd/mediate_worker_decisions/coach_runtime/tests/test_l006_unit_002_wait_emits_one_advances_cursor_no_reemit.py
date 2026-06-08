# URN: test:mediate-worker-decisions:coach-runtime:L006-UNIT-002-wait-emits-one-advances-cursor-no-reemit
# Acceptance: acc:mediate-worker-decisions:L006-UNIT-002-wait-emits-one-advances-cursor-no-reemit
# WMBT: wmbt:mediate-worker-decisions:L006
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""L006-UNIT-002 — wait emits one record, advances the cursor, never re-emits.

Over a REAL escalations.jsonl + file-backed cursor store: wait returns the next
appended record and persists the advanced cursor; a subsequent wait surfaces the
following record (never the handled one); a wait over an at-cursor ledger blocks
and returns None when the stop signal fires.
"""
from __future__ import annotations

import json

from atdd.mediate_worker_decisions.coach_runtime.src.application.coach_runtime import (
    CoachRuntime,
)
from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    ManagerRegistry,
)
from atdd.mediate_worker_decisions.coach_runtime.src.integration.jsonl_escalation_reader import (
    FileCursorStore,
    JsonlEscalationReader,
)
from atdd.mediate_worker_decisions.coach_runtime.tests._helpers import (
    CountingStop,
    FakeLiveness,
    ImmediateSleeper,
    RecordingCloser,
    RecordingSpawner,
    StubGate,
    fake_argv,
)

_A = {"escalation_id": "e-a", "request_id": "r-a", "cause": "worker_stuck"}
_B = {"escalation_id": "e-b", "request_id": "r-b", "cause": "dangerous_action"}


def _append(path, record):
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _runtime(tmp_path):
    return CoachRuntime(
        registry=ManagerRegistry(tmp_path / "reg"),
        spawner=RecordingSpawner(),
        liveness=FakeLiveness(),
        closer=RecordingCloser(),
        gate=StubGate(),
        daemon_argv=fake_argv,
    )


def test_wait_emits_one_advances_and_never_reemits(tmp_path):
    ledger = tmp_path / "escalations.jsonl"
    cursor_path = tmp_path / "wait.cursor"
    ledger.write_text("", encoding="utf-8")
    runtime = _runtime(tmp_path)

    reader = JsonlEscalationReader(ledger)
    cursor = FileCursorStore(cursor_path)

    _append(ledger, _A)
    first = runtime.wait_next(
        reader=reader, cursor_store=cursor, sleeper=ImmediateSleeper(),
        stop=CountingStop(false_polls=1), poll_interval=0.0,
    )
    assert first == _A
    assert FileCursorStore(cursor_path).load() == 1  # cursor advanced + persisted

    _append(ledger, _B)
    second = runtime.wait_next(
        reader=reader, cursor_store=cursor, sleeper=ImmediateSleeper(),
        stop=CountingStop(false_polls=1), poll_interval=0.0,
    )
    assert second == _B  # the following record, not a re-emit of _A
    assert FileCursorStore(cursor_path).load() == 2

    # Ledger now at cursor: wait blocks, then returns None when stop fires.
    third = runtime.wait_next(
        reader=reader, cursor_store=cursor, sleeper=ImmediateSleeper(),
        stop=CountingStop(false_polls=2), poll_interval=0.0,
    )
    assert third is None
    assert FileCursorStore(cursor_path).load() == 2  # nothing handled, no advance
