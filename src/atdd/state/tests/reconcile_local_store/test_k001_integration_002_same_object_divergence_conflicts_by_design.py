# URN: test:reconcile-local-store:verify-collaboration-flow:K001-INTEGRATION-002-same-object-divergence-conflicts-by-design
# Acceptance: acc:reconcile-local-store:K001-INTEGRATION-002-same-object-divergence-conflicts-by-design
# WMBT: wmbt:reconcile-local-store:K001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: when A and B transition the same uid to different phases, reconcile refuses to auto-merge, emits a conflict report, exits non-zero, retains B's backup and leaves B's store unchanged — no blind max-phase resolution occurs. Refs #1400.
"""Same-object divergence conflicts by design (K001-INTEGRATION-002).

wagon: reconcile-local-store | feature: verify-collaboration-flow | phase: RED
WMBT: wmbt:reconcile-local-store:K001

Disjoint objects merge silently — that is what the per-uid file layout buys. But when two
developers move the *same* object from the same starting phase to different places, there
is no merge that is both automatic and correct.

The tempting shortcut is to resolve by phase order: take whichever is "further along".
That is precisely what must not happen. A phase is a claim about evidence — that the tests
are red, that the code is green — and picking the higher one silently asserts evidence
nobody produced. Reconcile stops instead, hands the operator both sides, and keeps their
backup. Unsafe merges conflict by design (spec §11). Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import authoring, metadata, overlay
from atdd.state.projection import project, read_projection
from atdd.state.reconcile import (
    ReplayConflictError,
    hydrate_store,
    projection_path,
    reconcile,
    store_path,
)
from atdd.state.store import StateStore

from ._helpers import store
from ._live import commit_push, pull, two_developers


def _project_and_push(repo, message: str) -> str:
    conn = store(repo)
    try:
        result = project(StateStore(conn), projection_path(repo))
        overlay.mark_projected(conn, result.digest)
    finally:
        conn.close()
    return commit_push(repo, message)


def test_k001_integration_002_same_object_divergence_conflicts_by_design(tmp_path) -> None:
    """A and B move the same object differently: reconcile conflicts, and changes nothing."""
    _remote, dev_a, dev_b = two_developers(tmp_path)
    hydrate_store(dev_a)

    # A publishes a shared object at PLANNED, and B picks it up.
    conn = store(dev_a)
    try:
        shared = authoring.create_object(conn, slug="shared", owner_actor="dev-a").object_uid
        authoring.request_transition(conn, shared, "PLANNED")
    finally:
        conn.close()
    _project_and_push(dev_a, "A: shared object at PLANNED")

    pull(dev_b)
    hydrate_store(dev_b)
    conn = store(dev_b)
    try:
        assert StateStore(conn).objects.get(shared).state == "PLANNED"
        assert overlay.is_dirty(conn) is False
    finally:
        conn.close()

    # A transitions it PLANNED → GREEN and merges that to main.
    conn = store(dev_a)
    try:
        authoring.request_transition(conn, shared, "GREEN")
    finally:
        conn.close()
    a_head = _project_and_push(dev_a, "A: shared → GREEN")

    # B, from the same PLANNED, transitions it somewhere else entirely, and holds it.
    conn = store(dev_b)
    try:
        divergent = authoring.request_transition(conn, shared, "SMOKE")
        assert divergent.payload == {"from_phase": "PLANNED", "to_phase": "SMOKE"}
        b_base = metadata.base_commit(conn)
    finally:
        conn.close()

    # B pulls A's merge, then reconciles.
    new_head = pull(dev_b)
    assert new_head == a_head  # B fast-forwards onto A's merged commit
    before = store_path(dev_b).read_bytes()
    projection_before = read_projection(projection_path(dev_b))

    with pytest.raises(ReplayConflictError) as raised:
        reconcile(dev_b)

    report = raised.value.report

    # Reconcile refuses to auto-merge the divergent phase, and says why.
    assert len(report.conflicts) == 1
    conflict = report.conflicts[0]
    assert conflict.event.event_id == divergent.event_id
    assert conflict.event.object_uid == shared
    assert conflict.incoming["phase"] == "GREEN"     # what A merged
    assert "divergence" in conflict.reason
    assert "will not pick a winner by phase order" in conflict.reason

    # No blind max-phase resolution occurred: the store took neither A's GREEN nor B's
    # SMOKE. It is exactly where it was.
    conn = store(dev_b)
    try:
        assert StateStore(conn).objects.get(shared).state == "SMOKE"  # B's local view
        assert metadata.base_commit(conn) == b_base                   # anchor did NOT advance
        assert [e.event_id for e in overlay.replayable_events(conn)] == [divergent.event_id]
    finally:
        conn.close()

    # B's backup is retained and B's store is unchanged.
    assert report.backup_path is not None
    assert report.backup_path.exists()
    assert store_path(dev_b).read_bytes() == before
    assert read_projection(projection_path(dev_b)) == projection_before

    # The command exits non-zero so a hook or a script cannot mistake this for success.
    from atdd.state.reconcile_cli import dispatch

    class _Args:
        op, root, head, check_dirty = "reconcile", str(dev_b), None, False

    assert dispatch(_Args()) == 1
