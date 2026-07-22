# URN: test:reconcile-local-store:guard-dirty-store:C002-UNIT-002-empty-projection-never-empties-a-populated-store
# Acceptance: acc:reconcile-local-store:C002-UNIT-002-empty-projection-never-empties-a-populated-store
# WMBT: wmbt:reconcile-local-store:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: an existing-but-empty incoming projection refuses to hydrate a populated store, naming the count at stake, raising before any sqlite mutation; an empty projection against an empty store is still a legitimate no-op. Refs #1580.
"""An empty projection never empties a populated store (C002-UNIT-002).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C002

A projection directory that exists and holds nothing is a *claim* — unlike an absent one — but
it is the single least believable claim the shared truth can make against a store that holds
work. Every innocent explanation for it (a projection never generated, a checkout that never
carried one, a control root resolved somewhere unexpected, a half-finished clone) is far more
likely than "every object was legitimately retired at once", and the one guilty explanation
costs the entire store.

So it fails closed, and it fails closed *loudly*: the refusal names how many objects it was
about to destroy, because that number is what tells an operator whether they are looking at a
config mistake or a genuine mass retirement.

Empty-against-empty stays a no-op. A guard that refused a cold start would be a guard that
made ``atdd init`` impossible.

Refs #1580.
"""
from __future__ import annotations

import pytest

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.reconcile import MassDeletionRefused, hydrate_store, projection_path
from atdd.state.store import StateStore

from ._helpers import UID_A, UID_B, checkout, commit_all, document, store, store_bytes, write_projection


def test_c002_unit_002_empty_projection_never_empties_a_populated_store(tmp_path) -> None:
    """The refusal names the count at stake and leaves state.sqlite byte-identical."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A), document(UID_B)])
    commit_all(repo, "base projection")

    assert hydrate_store(repo)[0] == 2

    # Every projection file goes away, but the directory stays — the shared truth now
    # "says" the store should hold nothing at all.
    for path in projection_path(repo).glob("*.yaml"):
        path.unlink()
    commit_all(repo, "an empty projection reaches HEAD")
    before = store_bytes(repo)

    with pytest.raises(MassDeletionRefused) as refused:
        hydrate_store(repo)

    # The operator is told the size of what was refused, not merely that it was refused.
    message = str(refused.value)
    assert "2" in message, f"the refusal must name the count at stake: {message}"
    assert refused.value.existing == 2
    assert set(refused.value.doomed) == {UID_A, UID_B}

    # Nothing was mutated: raised before the first write.
    assert store_bytes(repo) == before
    conn = store(repo)
    try:
        assert {o.uid for o in StateStore(conn).objects.list(kind=WORK_ITEM_KIND)} == {UID_A, UID_B}
    finally:
        conn.close()


def test_c002_unit_002_empty_projection_against_an_empty_store_is_a_no_op(tmp_path) -> None:
    """A cold start has nothing to lose, so the guard must stay out of its way."""
    repo = checkout(tmp_path / "repo", )
    projection_path(repo).mkdir(parents=True, exist_ok=True)
    commit_all(repo, "empty projection, empty store")

    # No refusal, no objects, no drama — this is `atdd init` on a fresh checkout.
    hydrated, _base = hydrate_store(repo)
    assert hydrated == 0

    conn = store(repo)
    try:
        assert StateStore(conn).objects.list(kind=WORK_ITEM_KIND) == []
    finally:
        conn.close()
