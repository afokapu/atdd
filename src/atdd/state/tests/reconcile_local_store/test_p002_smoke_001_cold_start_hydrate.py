# URN: test:reconcile-local-store:hydrate-cold-store:P002-SMOKE-001-cold-start-hydrate
# Acceptance: acc:reconcile-local-store:P002-SMOKE-001-cold-start-hydrate
# WMBT: wmbt:reconcile-local-store:P002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — a fresh clone with no state.sqlite at all rebuilds its whole store from the committed projection through the real CLI, and a dirty unanchored store is refused with real remediation. Refs #1400.
"""SMOKE — cold start end-to-end through the real CLI (P002-SMOKE-001).

wagon: reconcile-local-store | feature: hydrate-cold-store | phase: SMOKE
WMBT: wmbt:reconcile-local-store:P002

A genuinely fresh clone: no store, no base commit, nothing but the checkout. If the model
is right, that is enough — the shared truth is in git, so a new developer needs nothing
handed to them out of band. This drives it through the real CLI to prove it. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import metadata
from atdd.state.reconcile import store_path

from ._helpers import UID_A, UID_B, document, store, write_projection
from ._live import atdd_state, bare_remote, clone, commit_push


@pytest.mark.smoke
def test_p002_smoke_001_cold_start_hydrate(tmp_path) -> None:
    """A fresh clone rebuilds its entire store from the committed projection alone."""
    remote = bare_remote(tmp_path)

    # One developer publishes a projection to the remote.
    author = clone(remote, tmp_path / "author")
    write_projection(
        author,
        [document(UID_A, phase="PLANNED", owner="dev-a"), document(UID_B, phase="RED", owner="dev-b")],
    )
    published = commit_push(author, "publish the projection")

    # A brand-new developer clones. They have no store at all.
    newcomer = clone(remote, tmp_path / "newcomer")
    assert not store_path(newcomer).exists()

    hydrated = atdd_state(newcomer, "hydrate")
    assert hydrated.returncode == 0, hydrated.stderr
    assert published in hydrated.stdout
    assert UID_A in hydrated.stdout and UID_B in hydrated.stdout

    # The projection alone rebuilt the store, and anchored it to the real HEAD.
    assert store_path(newcomer).exists()
    conn = store(newcomer)
    try:
        rows = {
            row["uid"]: row["state"]
            for row in conn.execute("SELECT uid, state FROM objects WHERE kind='work_item'")
        }
        assert rows == {UID_A: "PLANNED", UID_B: "RED"}
        assert metadata.base_commit(conn) == published
    finally:
        conn.close()

    fresh = atdd_state(newcomer, "freshness")
    assert fresh.returncode == 0
    assert "fresh" in fresh.stdout

    # The refusal half: a store that is dirty AND unanchored. Wipe the anchor, then
    # author privately — now neither hydrate nor reconcile may run.
    conn = store(newcomer)
    try:
        metadata.set(conn, metadata.BASE_COMMIT_KEY, None)
    finally:
        conn.close()

    created = atdd_state(newcomer, "object", "create", "--slug", "feature-y", "--owner", "dev-b")
    assert created.returncode == 0, created.stderr

    for verb in ("hydrate", "reconcile"):
        refused = atdd_state(newcomer, verb)
        assert refused.returncode == 1, f"{verb} should refuse a dirty, unanchored store"

        # And the remediation is real: it names both ways out, not a pointer to the
        # other command (which would refuse right back).
        assert "store_base_commit" in refused.stdout
        assert "atdd state project" in refused.stdout
        assert "discard" in refused.stdout
