# URN: test:mediate-worker-decisions:feed-daemon-durability:R004-SMOKE-001-real-run-replays-past-corrupt-tail
# Acceptance: acc:mediate-worker-decisions:R004-SMOKE-001-real-run-replays-past-corrupt-tail
# WMBT: wmbt:mediate-worker-decisions:R004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""R004-SMOKE-001 — a real on-disk run with a corrupt events tail still replays.

Drives the REAL ``JsonlPersistenceStore`` against a real on-disk run directory
(real files, the §4.6 durable run layout) holding several committed events plus a
truncated trailing line, then replays it through a fresh, independent store
instance and asserts every intact event is recovered — the run is NOT rendered
unreplayable by the one corrupt line.

Real infrastructure = the durable run files on disk; no external service needed,
so this smoke is runnable and provides the live RED→GREEN signal for B2.
"""
from __future__ import annotations

import pytest

from atdd.train.events import SCHEMA_VERSION
from atdd.train.persistence import JsonlPersistenceStore, load_conventions
from atdd.train.types import TrainEvent

from tests.coach._e040_helpers import build_temp_repo

pytestmark = pytest.mark.atdd_validator


def test_real_run_replays_past_corrupt_tail(tmp_path):
    repo = build_temp_repo(tmp_path)
    conventions = load_conventions(repo)

    writer = JsonlPersistenceStore(repo)
    run_id = writer.create_run(894, conventions=conventions)  # 1 valid event
    for i in range(3):
        writer.append_event(
            run_id,
            TrainEvent(
                schema_version=SCHEMA_VERSION,
                ts=f"2026-05-31T00:00:0{i}.000Z",
                run_id=run_id,
                issue_number=894,
                type="EvidenceMaterialized",
                payload={"i": i, "current_phase": "GREEN"},
                seq=i + 1,
            ),
        )

    events_file = repo / ".atdd" / "runtime" / "runs" / str(run_id) / "events.jsonl"
    intact = len([l for l in events_file.read_text().splitlines() if l.strip()])

    # Simulate a crash mid-write: a truncated trailing line on the real ledger.
    with events_file.open("a", encoding="utf-8") as fh:
        fh.write('{"schema_version": "1.0", "type": "Evidence')  # truncated

    # A fresh, independent store replays the real run past the corrupt tail.
    reader = JsonlPersistenceStore(repo)
    recovered = list(reader.replay_events(run_id))

    assert len(recovered) == intact, (
        f"replay recovered {len(recovered)} of {intact} intact events — the "
        f"corrupt tail line made the run unreplayable (B2)"
    )
    assert recovered[0].type == "RunStarted"
    assert [e.seq for e in recovered] == sorted(e.seq for e in recovered)
