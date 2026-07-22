# URN: test:reconcile-local-store:guard-dirty-store:C002-UNIT-001-missing-projection-refuses-before-deleting
# Acceptance: acc:reconcile-local-store:C002-UNIT-001-missing-projection-refuses-before-deleting
# WMBT: wmbt:reconcile-local-store:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: read_projection(require=True) raises MissingProjectionError for an absent directory instead of returning {}, and the hydrate path refuses before any sqlite mutation, leaving state.sqlite byte-identical. Refs #1580.
"""An absent projection directory is a refusal, not an empty set (C002-UNIT-001).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C002

``read_projection`` answered a missing directory with ``{}`` — the same value it gives for a
directory that exists and holds nothing. Those are different facts, and collapsing them is half
of what made the incident silent: "the shared truth says there are no objects" and "there is no
shared truth here" led to the same deletion, and only one of them is even an assertion.

So the two are separated. ``require=True`` — what reconcile passes — refuses an absent directory
by name. The permissive default is kept for the callers that legitimately mean "read whatever is
there": archival compaction and the canonicality check both run against directories that may
honestly be empty.

Refs #1580.
"""
from __future__ import annotations

import shutil

import pytest

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import MissingProjectionError, read_projection
from atdd.state.reconcile import MassDeletionRefused, hydrate_store, projection_path
from atdd.state.store import StateStore

from ._helpers import UID_A, UID_B, checkout, commit_all, document, store, store_bytes, write_projection


def test_c002_unit_001_absent_directory_is_refused_only_when_required(tmp_path) -> None:
    """``require=True`` names the absent directory; the default still returns ``{}``."""
    absent = tmp_path / "nowhere"

    # The permissive default is unchanged — compaction and canonicality depend on it.
    assert read_projection(absent) == {}

    # The required read refuses, and says which directory it wanted.
    with pytest.raises(MissingProjectionError) as refused:
        read_projection(absent, require=True)
    assert str(absent) in str(refused.value)

    # An *existing but empty* directory is a different fact: it reads as an empty set, because
    # it is a real (if trivial) assertion about the shared truth. The mass-deletion guard, not
    # this one, is what decides whether acting on it is safe.
    empty = tmp_path / "empty"
    empty.mkdir()
    assert read_projection(empty, require=True) == {}


def test_c002_unit_001_missing_projection_refuses_before_deleting(tmp_path) -> None:
    """A hydrate against a deleted projection directory refuses and mutates nothing.

    With work in the store the refusal is a :class:`MassDeletionRefused`, not the bare
    :class:`MissingProjectionError`. Both would protect the store; only one tells the
    operator what was at stake, and "there is no projection here" is a much less alarming
    sentence than it deserves to be when the answer to "and what did that nearly cost?"
    is the entire store.
    """
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A), document(UID_B)])
    commit_all(repo, "base projection")

    hydrated, _base = hydrate_store(repo)
    assert hydrated == 2

    # The projection goes away entirely — the incident's shape, and equally what a
    # mis-resolved control root produces when it points somewhere with no projection at all.
    shutil.rmtree(projection_path(repo))
    before = store_bytes(repo)

    with pytest.raises(MassDeletionRefused) as refused:
        hydrate_store(repo)

    # The refusal names both facts: the projection that is not there, and the work that
    # would have gone with it.
    message = str(refused.value)
    assert str(projection_path(repo)) in message
    assert "2" in message
    assert set(refused.value.doomed) == {UID_A, UID_B}
    # The precise cause is preserved for anyone reading the chain rather than the message.
    assert isinstance(refused.value.__cause__, MissingProjectionError)

    # Raised BEFORE any sqlite mutation: the store is byte-identical, both objects intact.
    assert store_bytes(repo) == before
    conn = store(repo)
    try:
        assert {o.uid for o in StateStore(conn).objects.list(kind=WORK_ITEM_KIND)} == {UID_A, UID_B}
    finally:
        conn.close()


def test_c002_unit_001_missing_projection_against_an_empty_store_is_a_plain_refusal(
    tmp_path,
) -> None:
    """With nothing at stake it is a misconfiguration, and says so without melodrama."""
    repo = checkout(tmp_path / "repo")
    commit_all(repo, "no projection was ever written")

    # Nothing in the store, so nothing to lose — the operator needs the diagnosis
    # ("your Control Root has no projection"), not a mass-deletion alarm.
    with pytest.raises(MissingProjectionError):
        hydrate_store(repo)
