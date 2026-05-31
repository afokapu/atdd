# URN: test:govern-lifecycle:extract-workflow-persistence-and-events-schema:E040-SMOKE-001-real-fs-run-roundtrip
# Acceptance: acc:govern-lifecycle:E040-SMOKE-001-real-fs-run-roundtrip
"""SMOKE test for E040-SMOKE-001 (docs/coach-decomposition.md §5.1, §6.3).

A real ``JsonlPersistenceStore`` rooted at a real temp repo writes real run files
to disk; a second, independently-constructed store reading the same run dir
replays the identical events and reconstructs the same ``RunState`` — proving
durability across instance boundaries against the real filesystem (no stub).
"""
from __future__ import annotations

import pytest

from atdd.coach.core.types import Phase, TransitionDecision, Verdict, VerdictKind
from atdd.train.events import SCHEMA_VERSION
from atdd.train.persistence import JsonlPersistenceStore, load_conventions
from atdd.train.types import TrainEvent

from tests.coach._e040_helpers import build_temp_repo

pytestmark = [pytest.mark.smoke]


def test_run_files_durable_across_store_instances(tmp_path):
    repo = build_temp_repo(tmp_path)
    conventions = load_conventions(repo)

    # First store: write a run to disk.
    writer = JsonlPersistenceStore(repo)
    run_id = writer.create_run(894, conventions=conventions)
    writer.append_event(
        run_id,
        TrainEvent(
            schema_version=SCHEMA_VERSION,
            ts="2026-05-31T00:00:01.000Z",
            run_id=run_id,
            issue_number=894,
            type="EvidenceMaterialized",
            payload={"evidence_hash": "h", "current_phase": "GREEN"},
            seq=0,
        ),
    )
    writer.append_decision(
        run_id,
        TransitionDecision(
            from_phase=Phase.GREEN,
            to_phase=Phase.SMOKE,
            persona=None,
            prompt_template_id=None,
            evidence_keys_required=(),
            verdict=Verdict(kind=VerdictKind.PROCEED, reason="ok", rule_ids=("r",)),
        ),
        evidence_hash="h",
    )

    run_dir = repo / ".atdd" / "runtime" / "runs" / str(run_id)
    for name in ("events.jsonl", "decisions.jsonl", "conventions.snapshot.yaml", "conventions.hash"):
        assert (run_dir / name).is_file(), f"real on-disk {name} must exist"

    # Second, independent store instance over the same root.
    reader = JsonlPersistenceStore(repo)
    reader_events = [(e.seq, e.type) for e in reader.replay_events(run_id)]
    writer_events = [(e.seq, e.type) for e in writer.replay_events(run_id)]
    assert reader_events == writer_events

    reconstructed = reader.load_run(run_id)
    original = writer.load_run(run_id)
    assert reconstructed.run_id == original.run_id == run_id
    assert reconstructed.issue_number == original.issue_number == 894
    assert reconstructed.conventions_hash == original.conventions_hash == conventions.snapshot_hash
    assert reconstructed.last_event_seq == original.last_event_seq
