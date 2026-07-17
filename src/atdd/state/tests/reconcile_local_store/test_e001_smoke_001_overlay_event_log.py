# URN: test:reconcile-local-store:record-overlay-events:E001-SMOKE-001-overlay-event-log
# Acceptance: acc:reconcile-local-store:E001-SMOKE-001-overlay-event-log
# WMBT: wmbt:reconcile-local-store:E001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — real `atdd state object create` / `atdd state author` commands append real overlay events to a real .atdd/state/state.sqlite, and `atdd state overlay` lists them. Refs #1400.
"""SMOKE — the overlay event log end-to-end through the real CLI (E001-SMOKE-001).

wagon: reconcile-local-store | feature: record-overlay-events | phase: SMOKE
WMBT: wmbt:reconcile-local-store:E001

No mocks and no manual patching: real authoring commands driven by subprocess against
a real checkout, writing real rows into a real store. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import overlay

from ._helpers import checkout, store
from ._live import atdd_state


@pytest.mark.smoke
def test_e001_smoke_001_overlay_event_log(tmp_path) -> None:
    """Real authoring commands leave real, typed, ordered overlay events behind."""
    repo = checkout(tmp_path / "repo")
    assert atdd_state(repo, "init").returncode == 0

    created = atdd_state(repo, "object", "create", "--slug", "feature-y", "--owner", "dev-b")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    for args in (
        ("author", "body", uid, "--body", "the body"),
        ("author", "transition", uid, "--to", "PLANNED"),
        ("author", "train", uid, "--train", "train:commons:spine"),
    ):
        result = atdd_state(repo, *args)
        assert result.returncode == 0, result.stderr

    # The real store holds one typed, ordered event per command.
    conn = store(repo)
    try:
        events = overlay.all_events(conn)
        assert [e.kind for e in events] == [
            overlay.OBJECT_CREATED,
            overlay.BODY_UPDATED,
            overlay.PHASE_TRANSITION_REQUESTED,
            overlay.TRAIN_UPDATED,
        ]
        assert [e.seq for e in events] == [1, 2, 3, 4]
        assert all(e.object_uid == uid for e in events)
        assert overlay.is_dirty(conn) is True
    finally:
        conn.close()

    # The CLI reports them, so an operator can see what their store is holding.
    listed = atdd_state(repo, "overlay")
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.count(uid) == 4
    assert "phase_transition_requested" in listed.stdout
    assert "4 overlay event(s)" in listed.stdout
