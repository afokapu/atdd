# URN: test:reconcile-local-store:track-base-commit:P001-SMOKE-001-store-base-commit
# Acceptance: acc:reconcile-local-store:P001-SMOKE-001-store-base-commit
# WMBT: wmbt:reconcile-local-store:P001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state hydrate` CLI stamps store_base_commit into a real .atdd/state/state.sqlite, and `atdd state freshness` reads it back against a real HEAD. Refs #1400.
"""SMOKE — store-base-commit end-to-end through the real CLI (P001-SMOKE-001).

wagon: reconcile-local-store | feature: track-base-commit | phase: SMOKE
WMBT: wmbt:reconcile-local-store:P001

No mocks and no manual patching: a real git checkout, the real ``atdd state`` CLI
driven by subprocess, and a real ``.atdd/state/state.sqlite``. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import metadata

from ._helpers import UID_A, commit_all, document, head, store, write_projection
from ._live import atdd_state


@pytest.mark.smoke
def test_p001_smoke_001_store_base_commit(tmp_path) -> None:
    """The real CLI stamps the real store with the real HEAD, and reports it fresh."""
    from ._helpers import checkout

    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED")])
    commit = commit_all(repo, "projection")

    hydrated = atdd_state(repo, "hydrate")
    assert hydrated.returncode == 0, hydrated.stderr
    assert commit in hydrated.stdout

    # The stamp landed in the real store on disk, not in a fixture.
    conn = store(repo)
    try:
        assert metadata.base_commit(conn) == commit
    finally:
        conn.close()

    # The CLI reads it back and calls the store fresh at HEAD.
    fresh = atdd_state(repo, "freshness")
    assert fresh.returncode == 0, fresh.stdout
    assert "fresh" in fresh.stdout

    # Moving HEAD without reconciling leaves the anchor behind — and the CLI says so.
    moved = commit_all(repo, "another commit")
    assert moved == head(repo) != commit

    stale = atdd_state(repo, "freshness")
    assert stale.returncode == 1
    assert "STALE" in stale.stdout
    assert commit[:12] in stale.stdout
