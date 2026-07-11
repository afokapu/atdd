# URN: test:reconcile-local-store:reconcile-store-state:R001-SMOKE-001-overlay-replay
# Acceptance: acc:reconcile-local-store:R001-SMOKE-001-overlay-replay
# WMBT: wmbt:reconcile-local-store:R001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state reconcile` CLI hydrates the incoming projection into a real store, replays the real overlay on top, re-projects the affected object and advances store_base_commit to the real HEAD. Refs #1400.
"""SMOKE — overlay replay end-to-end through the real CLI (R001-SMOKE-001).

wagon: reconcile-local-store | feature: reconcile-store-state | phase: SMOKE
WMBT: wmbt:reconcile-local-store:R001

A real checkout, the real ``atdd state`` CLI by subprocess, and a real
``.atdd/state/state.sqlite``. No mocks, no manual patching. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import metadata

from ._helpers import UID_A, UID_B, checkout, commit_all, document, head, store, write_projection
from ._live import atdd_state


@pytest.mark.smoke
def test_r001_smoke_001_overlay_replay(tmp_path) -> None:
    """The real CLI replays real overlay onto a real incoming projection."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED", owner="dev-a")])
    base = commit_all(repo, "base projection")
    assert atdd_state(repo, "hydrate").returncode == 0

    # Real private authoring: a new object, then a transition on it.
    created = atdd_state(repo, "object", "create", "--slug", "feature-y", "--owner", "dev-b")
    assert created.returncode == 0, created.stderr
    local_uid = created.stdout.strip()
    assert atdd_state(repo, "author", "transition", local_uid, "--to", "PLANNED").returncode == 0

    # A peer's merged work arrives at a new HEAD, touching disjoint objects.
    write_projection(
        repo,
        [document(UID_A, phase="GREEN", owner="dev-a"), document(UID_B, phase="RED", owner="dev-a")],
    )
    new_head = commit_all(repo, "peer merged work")
    assert new_head == head(repo) != base

    reconciled = atdd_state(repo, "reconcile")
    assert reconciled.returncode == 0, reconciled.stdout + reconciled.stderr
    assert "replay" in reconciled.stdout
    assert base[:12] in reconciled.stdout and new_head[:12] in reconciled.stdout

    # The real store holds hydrate(incoming) + replay(overlay), anchored at the new HEAD.
    conn = store(repo)
    try:
        rows = {
            row["uid"]: row["state"]
            for row in conn.execute("SELECT uid, state FROM objects WHERE kind='work_item'")
        }
        assert rows[UID_A] == "GREEN"       # the peer's advance landed
        assert rows[UID_B] == "RED"         # the peer's new object arrived
        assert rows[local_uid] == "PLANNED" # the private work survived
        assert metadata.base_commit(conn) == new_head
    finally:
        conn.close()

    # The affected object was re-projected: it now has a real projection file on disk.
    assert (repo / ".atdd" / "state" / "projection" / f"{local_uid}.yaml").exists()

    # And the store is now fresh at HEAD.
    fresh = atdd_state(repo, "freshness")
    assert fresh.returncode == 0
    assert "fresh" in fresh.stdout
