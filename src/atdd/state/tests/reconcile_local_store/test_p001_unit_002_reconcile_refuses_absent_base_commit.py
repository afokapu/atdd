# URN: test:reconcile-local-store:track-base-commit:P001-UNIT-002-reconcile-refuses-absent-base-commit
# Acceptance: acc:reconcile-local-store:P001-UNIT-002-reconcile-refuses-absent-base-commit
# WMBT: wmbt:reconcile-local-store:P001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: reconcile refuses a store whose store_base_commit is absent or names an unreachable commit — StoreBaseCommitError, no sqlite mutation, and the operator told to re-hydrate. Refs #1400.
"""A store with no resolvable anchor is not reconcilable (P001-UNIT-002).

wagon: reconcile-local-store | feature: track-base-commit | phase: RED
WMBT: wmbt:reconcile-local-store:P001

Reconcile replays the local overlay onto the incoming projection *relative to a
base*. With no base — or a base this repository no longer carries, after a hard reset
or a discarded branch — there is nothing to replay onto. Inventing one would apply the
developer's private work to the wrong public state, silently. So reconcile refuses,
and sends them to re-hydrate. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import metadata
from atdd.state.metadata import StoreBaseCommitError
from atdd.state.reconcile import reconcile

from ._helpers import UID_A, checkout, commit_all, document, store, store_bytes, write_projection

#: A well-formed sha that names no object in the fixture repository.
_UNKNOWN = "0" * 40


def test_p001_unit_002_reconcile_refuses_absent_base_commit(tmp_path) -> None:
    """Absent and unresolvable base commits both raise, and neither mutates sqlite."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A)])
    commit_all(repo, "projection")

    # A store that exists but was never anchored: it carries no store_base_commit.
    conn = store(repo)
    try:
        assert metadata.base_commit(conn) is None
    finally:
        conn.close()
    before = store_bytes(repo)

    with pytest.raises(StoreBaseCommitError) as absent:
        reconcile(repo)

    # The refusal names the missing commit and tells the operator to re-hydrate.
    assert absent.value.commit is None
    assert "store_base_commit" in str(absent.value)
    assert "hydrate" in str(absent.value)

    # No sqlite mutation was attempted.
    assert store_bytes(repo) == before

    # Now anchor the store to a commit this repository does not have.
    conn = store(repo)
    try:
        metadata.stamp_base_commit(conn, _UNKNOWN)
    finally:
        conn.close()
    anchored = store_bytes(repo)

    with pytest.raises(StoreBaseCommitError) as unknown:
        reconcile(repo)

    # The refusal names the *unresolvable* commit, not merely "a" commit.
    assert unknown.value.commit == _UNKNOWN
    assert _UNKNOWN in str(unknown.value)
    assert "hydrate" in str(unknown.value)

    # Still no mutation: the store is byte-identical to its pre-call content.
    assert store_bytes(repo) == anchored
