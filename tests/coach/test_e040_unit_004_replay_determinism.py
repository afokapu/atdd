# URN: test:govern-lifecycle:extract-workflow-persistence-and-events-schema:E040-UNIT-004-replay-determinism
# Acceptance: acc:govern-lifecycle:E040-UNIT-004-replay-determinism
"""Unit test for E040-UNIT-004 (docs/coach-decomposition.md §6.3, §5.2).

Replay is deterministic: reconstructing the store mid-loop from the persisted
event log and re-running the pure Coach-core decisions over the materialized
phases reproduces the identical decision list.
"""
from __future__ import annotations

import pytest

from atdd.coach import core as coach_core
from atdd.coach.core.types import (
    CiState,
    Evidence,
    IssueType,
    Phase,
)
from atdd.train.events import SCHEMA_VERSION
from atdd.train.persistence import JsonlPersistenceStore, load_conventions
from atdd.train.types import TrainEvent

from tests.coach._e040_helpers import build_temp_repo

pytestmark = pytest.mark.atdd_validator

_DRIVEN_PHASES = (Phase.PLANNED, Phase.RED, Phase.GREEN)


def _evidence_at(phase: Phase, conventions_hash: str) -> Evidence:
    """Deterministic synthetic evidence — clean CI, no blockers → PROCEED."""
    return Evidence(
        issue_number=894,
        issue_type=IssueType.IMPLEMENTATION,
        current_phase=phase,
        train_id="0001-self-compliance-validate",
        branch="feat/extract-workflow-persistence-and-events-schema",
        wmbts=(),
        validator_reports=(),
        ci_state=CiState.SUCCESS,
        pr_state=None,
        last_commit_sha="0" * 40,
        artifacts_present=frozenset(),
        elapsed_in_phase_seconds=0,
        conventions_hash=conventions_hash,
    )


def _drive(store, run_id, conventions):
    """Simulate the runner loop: materialize → decide, recording each decision."""
    decisions = []
    for phase in _DRIVEN_PHASES:
        store.append_event(
            run_id,
            TrainEvent(
                schema_version=SCHEMA_VERSION,
                ts="2026-05-31T00:00:00.000Z",
                run_id=run_id,
                issue_number=894,
                type="EvidenceMaterialized",
                payload={"evidence_hash": "h", "current_phase": phase.value},
                seq=0,
            ),
        )
        decision = coach_core.next_transition(_evidence_at(phase, conventions.snapshot_hash), conventions)
        store.append_decision(run_id, decision, evidence_hash="h")
        decisions.append(decision)
    return decisions


def test_replay_reproduces_identical_decisions(tmp_path):
    repo = build_temp_repo(tmp_path)
    conventions = load_conventions(repo)

    store1 = JsonlPersistenceStore(repo)
    run_id = store1.create_run(894, conventions=conventions)
    original_decisions = _drive(store1, run_id, conventions)
    assert all(d.verdict.kind.value == "proceed" for d in original_decisions)

    events1 = list(store1.replay_events(run_id))

    # Drop and recreate the store against the same on-disk run dir.
    store2 = JsonlPersistenceStore(repo)
    events2 = list(store2.replay_events(run_id))

    # The persisted event stream replays identically.
    assert [(e.seq, e.type, e.payload) for e in events2] == [
        (e.seq, e.type, e.payload) for e in events1
    ]

    # Re-run the pure decisions over the REPLAYED materialized phases.
    replayed_phases = [
        Phase(e.payload["current_phase"])
        for e in events2
        if e.type == "EvidenceMaterialized"
    ]
    assert replayed_phases == list(_DRIVEN_PHASES)
    replay_decisions = [
        coach_core.next_transition(_evidence_at(p, conventions.snapshot_hash), conventions)
        for p in replayed_phases
    ]

    assert replay_decisions == original_decisions
