# URN: test:reconcile-local-store:reconcile-store-state:R002-SMOKE-001-conflict-report
# Acceptance: acc:reconcile-local-store:R002-SMOKE-001-conflict-report
# WMBT: wmbt:reconcile-local-store:R002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — a real conflicting reconcile through the real CLI exits non-zero, prints a report naming the offending event, the incoming state and the retained backup path, and leaves the real state.sqlite byte-identical. Refs #1400.
"""SMOKE — the conflict report end-to-end through the real CLI (R002-SMOKE-001).

wagon: reconcile-local-store | feature: reconcile-store-state | phase: SMOKE
WMBT: wmbt:reconcile-local-store:R002

A real checkout, the real CLI, a real store, and a real conflict. The exit code is the
part that matters most here: a hook or a script must be able to tell a conflicted
reconcile from a successful one without parsing prose. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import metadata

from ._helpers import UID_A, checkout, commit_all, document, store, store_bytes, write_projection
from ._live import atdd_state


@pytest.mark.smoke
def test_r002_smoke_001_conflict_report(tmp_path) -> None:
    """The real CLI conflicts loudly, keeps the backup, and changes nothing."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED", owner="dev-a")])
    base = commit_all(repo, "base projection")
    assert atdd_state(repo, "hydrate").returncode == 0

    # B authors a transition from PLANNED.
    authored = atdd_state(repo, "author", "transition", UID_A, "--to", "GREEN")
    assert authored.returncode == 0, authored.stderr

    # A merges a DIFFERENT transition on the same object first.
    write_projection(repo, [document(UID_A, phase="SMOKE", owner="dev-a")])
    commit_all(repo, "A merged a divergent transition")

    before = store_bytes(repo)

    conflicted = atdd_state(repo, "reconcile")

    # The command exits non-zero.
    assert conflicted.returncode == 1

    # The report names the offending event, its object and kind, and says why.
    assert "CONFLICT" in conflicted.stdout
    assert UID_A in conflicted.stdout
    assert "phase_transition_requested" in conflicted.stdout
    assert "divergence" in conflicted.stdout

    # It shows the incoming projection state for that object.
    assert "'SMOKE'" in conflicted.stdout

    # It names the retained sqlite backup path — and that file really is there.
    backups = list((repo / ".atdd" / "state").glob("state.sqlite.bak*"))
    assert len(backups) == 1
    assert str(backups[0]) in conflicted.stdout
    assert backups[0].read_bytes() == before

    # The real store is byte-identical, and still anchored at the OLD base commit.
    assert store_bytes(repo) == before
    conn = store(repo)
    try:
        assert metadata.base_commit(conn) == base
    finally:
        conn.close()
