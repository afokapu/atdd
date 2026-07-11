# URN: test:reconcile-local-store:guard-dirty-store:C001-SMOKE-001-dirty-store-overwrite
# Acceptance: acc:reconcile-local-store:C001-SMOKE-001-dirty-store-overwrite
# WMBT: wmbt:reconcile-local-store:C001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state hydrate` CLI refuses to overwrite a real dirty store and exits non-zero, while the real `atdd state reconcile` backs it up and keeps the private work. Refs #1400.
"""SMOKE — the dirty-store gate end-to-end through the real CLI (C001-SMOKE-001).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: SMOKE
WMBT: wmbt:reconcile-local-store:C001

No mocks and no manual patching: a real checkout, the real CLI, and a real
``.atdd/state/state.sqlite`` holding real uncommitted overlay. Refs #1400.
"""
from __future__ import annotations

import pytest

from ._helpers import UID_A, UID_B, checkout, commit_all, document, store_bytes, write_projection
from ._live import atdd_state


@pytest.mark.smoke
def test_c001_smoke_001_dirty_store_overwrite(tmp_path) -> None:
    """The real CLI refuses to overwrite a dirty store, and reconcile preserves the work."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED")])
    commit_all(repo, "base projection")

    assert atdd_state(repo, "hydrate").returncode == 0

    # Real private authoring through the real CLI.
    created = atdd_state(repo, "object", "create", "--slug", "feature-y", "--owner", "dev-b")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    # A peer's work arrives at a new HEAD.
    write_projection(repo, [document(UID_A, phase="GREEN"), document(UID_B)])
    commit_all(repo, "peer work")

    before = store_bytes(repo)

    # The overwrite path refuses, exits non-zero, and names what would be lost.
    refused = atdd_state(repo, "hydrate")
    assert refused.returncode == 1
    assert "dirty" in refused.stdout
    assert uid in refused.stdout
    assert "reconcile" in refused.stdout

    # The real store on disk is byte-identical: the refusal cost nothing.
    assert store_bytes(repo) == before

    # Reconcile — the path that does NOT overwrite — succeeds and keeps the work.
    reconciled = atdd_state(repo, "reconcile")
    assert reconciled.returncode == 0, reconciled.stdout + reconciled.stderr
    assert "replay" in reconciled.stdout
    assert "backup" in reconciled.stdout

    # A real backup file was left on disk, and the private object survived.
    assert list((repo / ".atdd" / "state").glob("state.sqlite.bak*"))

    overlay_after = atdd_state(repo, "overlay", "--all")
    assert overlay_after.returncode == 0
    assert uid in overlay_after.stdout
