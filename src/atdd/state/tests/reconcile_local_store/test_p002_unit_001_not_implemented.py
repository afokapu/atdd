# URN: test:reconcile-local-store:hydrate-cold-store:P002-UNIT-001-not-implemented
# Acceptance: acc:reconcile-local-store:P002-UNIT-001-not-implemented
# WMBT: wmbt:reconcile-local-store:P002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the refusal half of cold-start-hydrate — a store missing its base commit but carrying overlay events is refused by BOTH hydrate and reconcile with remediation, never bounced between them and never silently overwritten. Refs #1400.
"""Cold start is NOT available to a dirty, unanchored store (P002-UNIT-001).

wagon: reconcile-local-store | feature: hydrate-cold-store | phase: RED
WMBT: wmbt:reconcile-local-store:P002

The WMBT pairs a success branch with a refusal branch: cold-start hydrate succeeds when
no store or no base commit exists **and no overlay is present**, "while refusing and
emitting remediation when a store is missing its base commit but carries overlay events".
This acceptance is that refusal branch — the case cold start does *not* cover.

It is the one state that can trap an operator. Hydrate refuses because the store is
dirty and points at reconcile; reconcile refuses because there is no base and points
back at hydrate. Two commands each blaming the other is not a refusal, it is a loop. So
both refuse with the *same* actionable remedy: the work has no anchor because it was
never shared — share it, or drop it. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import authoring, metadata, overlay
from atdd.state.reconcile import ColdStartError, hydrate_store, reconcile

from ._helpers import UID_A, checkout, commit_all, document, store, store_bytes, write_projection


def test_p002_unit_001_not_implemented(tmp_path) -> None:
    """A baseless store carrying overlay is refused by both paths, with a way out."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED")])
    commit_all(repo, "projection")

    # A store that was never anchored, but carries private authoring anyway.
    conn = store(repo)
    try:
        created = authoring.create_object(conn, slug="feature-y", owner_actor="dev-b")
        assert metadata.base_commit(conn) is None
        assert overlay.is_dirty(conn) is True
    finally:
        conn.close()

    before = store_bytes(repo)

    # Hydrate refuses: overwriting would lose work that exists nowhere else.
    with pytest.raises(ColdStartError) as hydrated:
        hydrate_store(repo)

    # Reconcile refuses too — and with the SAME error, not a pointer back to hydrate.
    with pytest.raises(ColdStartError) as reconciled:
        reconcile(repo)

    for raised in (hydrated, reconciled):
        message = str(raised.value)
        assert raised.value.commit is None
        assert [e.event_id for e in raised.value.events] == [created.event_id]

        # The remediation is concrete and names both real choices — keep it, or drop it.
        assert "store_base_commit" in message
        assert "atdd state project" in message  # keep the work: share it
        assert "discard" in message              # or drop it, deliberately
        assert "cannot be hydrated" in message

    # Neither refusal touched the store: the private work is entirely intact.
    assert store_bytes(repo) == before
    conn = store(repo)
    try:
        assert [e.event_id for e in overlay.replayable_events(conn)] == [created.event_id]
        assert metadata.base_commit(conn) is None
    finally:
        conn.close()
