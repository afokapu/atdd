# URN: test:govern-lifecycle:extract-workflow-persistence-and-events-schema:E040-UNIT-001-jsonl-persistence-store-run-lifecycle
# Acceptance: acc:govern-lifecycle:E040-UNIT-001-jsonl-persistence-store-run-lifecycle
"""Unit test for E040-UNIT-001 (docs/coach-decomposition.md §4.6, §5.1, §5.2).

``JsonlPersistenceStore`` fulfils the §4.6 ``PersistenceStore`` Protocol with
durable on-disk runs: ``create_run`` writes the run scaffold (RunStarted event +
conventions snapshot + hash), events/decisions append and replay, ``load_run``
reconstructs ``RunState``, and the manifest round-trips via get/upsert_issue.
"""
from __future__ import annotations

import json

import pytest

from atdd.coach.core.types import Phase, TransitionDecision, Verdict, VerdictKind
from atdd.train.events import SCHEMA_VERSION
from atdd.train.persistence import (
    IssueRecord,
    JsonlPersistenceStore,
    PersistenceStore,
    load_conventions,
)
from atdd.train.types import TrainEvent

from tests.coach._e040_helpers import build_temp_repo

pytestmark = pytest.mark.atdd_validator


def _store(tmp_path):
    repo = build_temp_repo(tmp_path)
    return JsonlPersistenceStore(repo), load_conventions(repo), repo


def test_store_satisfies_persistence_protocol(tmp_path):
    store, _conv, _repo = _store(tmp_path)
    assert isinstance(store, PersistenceStore)


def test_create_run_writes_snapshot_hash_and_runstarted(tmp_path):
    store, conventions, repo = _store(tmp_path)
    run_id = store.create_run(894, conventions=conventions)

    run_dir = repo / ".atdd" / "runtime" / "runs" / str(run_id)
    snapshot = run_dir / "conventions.snapshot.yaml"
    hash_file = run_dir / "conventions.hash"
    events_file = run_dir / "events.jsonl"
    assert snapshot.is_file(), "create_run must write conventions.snapshot.yaml"
    assert hash_file.is_file(), "create_run must write conventions.hash"
    assert hash_file.read_text().strip() == conventions.snapshot_hash

    first = json.loads(events_file.read_text().splitlines()[0])
    assert first["type"] == "RunStarted"
    assert first["schema_version"] == SCHEMA_VERSION
    for key in ("conventions_hash", "conventions_snapshot_ref", "policy_handle_id"):
        assert key in first["payload"], f"RunStarted payload missing {key!r}"
    assert first["payload"]["conventions_hash"] == conventions.snapshot_hash


def test_append_and_replay_events_in_seq_order(tmp_path):
    store, conventions, _repo = _store(tmp_path)
    run_id = store.create_run(894, conventions=conventions)

    for i, etype in enumerate(("EvidenceMaterialized", "DecisionMade"), start=1):
        store.append_event(
            run_id,
            TrainEvent(
                schema_version=SCHEMA_VERSION,
                ts="2026-05-31T00:00:0%d.000Z" % i,
                run_id=run_id,
                issue_number=894,
                type=etype,
                payload={"current_phase": "GREEN"} if etype == "EvidenceMaterialized"
                else {"verdict_kind": "proceed", "from_phase": "GREEN",
                      "to_phase": "SMOKE", "persona": "tester", "rule_ids": []},
                seq=0,  # store assigns the authoritative seq
            ),
        )

    replayed = list(store.replay_events(run_id))
    types = [e.type for e in replayed]
    assert types[0] == "RunStarted"
    assert "EvidenceMaterialized" in types and "DecisionMade" in types
    seqs = [e.seq for e in replayed]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), "seq must be monotonic+unique"


def test_append_decision_persists_with_evidence_hash(tmp_path):
    store, conventions, repo = _store(tmp_path)
    run_id = store.create_run(894, conventions=conventions)
    decision = TransitionDecision(
        from_phase=Phase.GREEN,
        to_phase=Phase.SMOKE,
        persona=None,
        prompt_template_id=None,
        evidence_keys_required=(),
        verdict=Verdict(kind=VerdictKind.PROCEED, reason="ok", rule_ids=("r",)),
    )
    store.append_decision(run_id, decision, evidence_hash="abc123")

    decisions_file = repo / ".atdd" / "runtime" / "runs" / str(run_id) / "decisions.jsonl"
    assert decisions_file.is_file()
    row = json.loads(decisions_file.read_text().splitlines()[0])
    assert row["evidence_hash"] == "abc123"


def test_load_run_reconstructs_runstate(tmp_path):
    store, conventions, _repo = _store(tmp_path)
    run_id = store.create_run(894, conventions=conventions)

    state = store.load_run(run_id)
    assert state.run_id == run_id
    assert state.issue_number == 894
    assert state.conventions_hash == conventions.snapshot_hash
    assert state.current_phase == Phase.GREEN  # seeded from the manifest status
    assert state.last_event_seq >= 1


def test_upsert_then_get_issue_roundtrips(tmp_path):
    store, _conv, _repo = _store(tmp_path)
    rec = store.get_issue(894)
    assert isinstance(rec, IssueRecord)
    assert rec.issue_number == 894

    updated = IssueRecord(
        id=rec.id, slug=rec.slug, issue_number=894,
        type=rec.type, status=Phase.SMOKE, train=rec.train,
        created=rec.created, archived=rec.archived,
    )
    store.upsert_issue(updated)
    assert store.get_issue(894).status == Phase.SMOKE
