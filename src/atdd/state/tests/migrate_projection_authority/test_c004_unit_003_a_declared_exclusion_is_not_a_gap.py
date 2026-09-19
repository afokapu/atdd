# URN: test:migrate-projection-authority:migrate-store-projection:C004-UNIT-003-a-declared-exclusion-is-not-a-gap
# Acceptance: acc:migrate-projection-authority:C004-UNIT-003-a-declared-exclusion-is-not-a-gap
# WMBT: wmbt:migrate-projection-authority:C004
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A COMPLETE work item and a non-work_item object are absent from the projection by a DECLARED rule, not by loss — the criterion stays MET, the census assigns every stored object to exactly one bucket and sums to the store, and the obligation derives from the same rules the projector applies so the two cannot drift. Refs #2042.
"""An exclusion is not a gap, and the census must prove it (C004-UNIT-003).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C004

The lab found the store→projection gap is *entirely* declared: `ARCHIVED_PHASES` holds
back COMPLETE work items, whose completion is derived from merge-to-main so they have no
legal projection document, and `build_documents` lists `kind=work_item` only. The residual
over the live corpus was zero.

So a coverage check that flagged those would be wrong in the opposite direction — it would
refuse every real repo, get switched off, and leave the actual defect uncaught. The check
has to know the difference between *declined* and *dropped*.

The census is the second half, and it is what makes the residual **provable** rather than
merely explained: every stored object lands in exactly one bucket and the buckets sum to
the store's population. No expected total is written here — the sum is compared against the
store this test seeds, so the acceptance is correct at any population. The live corpus grew
1,053 → 1,064 in two days; a test that baked a number would already be wrong.

The third assertion is the anti-drift one: the obligation must be derived from the same
rules `build_documents` applies, not restated. A separately-written obligation is a second
implementation, and the two diverge the first time someone changes a filter.
"""
from __future__ import annotations

from atdd.state import cutover
from atdd.state.projection import ARCHIVED_PHASES, WORK_ITEM_KIND

from ._coverage_helpers import new_repo, project_and_commit, require, seed

_ARCHIVED_PHASE = ARCHIVED_PHASES[0]
_FOREIGN_UID = "agent-session-not-a-work-item"


def _store(root):
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    return StateStore(connect(init_state_store(start=root)))


def test_objects_excluded_by_a_declared_rule_are_not_coverage_gaps(tmp_path) -> None:
    """A COMPLETE work item and a foreign kind are absent by rule; the criterion still passes."""
    root = new_repo(tmp_path / "checkout")
    minted = seed(
        root,
        [("live-item", "PLANNED"), ("finished-item", _ARCHIVED_PHASE)],
        other_kinds=[(_FOREIGN_UID, "agent_session")],
    )
    out = project_and_commit(root)
    store = _store(root)

    obliged = require("projectable_uids")(store)
    assert minted["live-item"] in obliged
    assert minted["finished-item"] not in obliged, (
        f"a {_ARCHIVED_PHASE} work item has no legal projection document, so it cannot be "
        "part of the coverage obligation"
    )
    assert _FOREIGN_UID not in obliged, "a non-work_item object was never a candidate"

    criterion = cutover.check(root, projection_dir=out).criteria[0]
    assert criterion.met, (
        "objects excluded by a declared rule were reported as coverage gaps. A check that "
        f"refuses every real repo gets switched off. Blockers: {criterion.blockers}"
    )


def test_the_census_accounts_for_every_stored_object(tmp_path) -> None:
    """Every object lands in exactly one bucket, and the buckets sum to the store."""
    root = new_repo(tmp_path / "checkout")
    seed(
        root,
        [("one", "PLANNED"), ("two", "RED"), ("three", _ARCHIVED_PHASE)],
        other_kinds=[(_FOREIGN_UID, "agent_session"), ("wmbt-thing", "wmbt")],
    )
    project_and_commit(root)
    store = _store(root)

    census = require("coverage_census")(store)
    total = len(store.objects.list())

    assert census.residual == [], (
        f"objects the projector neither emits nor declines by a named rule: {census.residual}"
    )
    assert sum(census.buckets.values()) == total, (
        f"the census sums to {sum(census.buckets.values())} but the store holds {total} — "
        "an object is being counted twice or not at all, so the residual proves nothing"
    )
    assert any(f"kind={WORK_ITEM_KIND}" not in name and "kind=" in name
               for name in census.buckets), "the census must name the kind exclusions"
    assert any(_ARCHIVED_PHASE in name for name in census.buckets), (
        "the census must name the archived-phase exclusion, since that is the largest bucket "
        "in the live corpus and the one most likely to be mistaken for loss"
    )
