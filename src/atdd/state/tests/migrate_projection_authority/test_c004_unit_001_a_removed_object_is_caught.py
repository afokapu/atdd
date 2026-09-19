# URN: test:migrate-projection-authority:migrate-store-projection:C004-UNIT-001-a-removed-object-is-caught
# Acceptance: acc:migrate-projection-authority:C004-UNIT-001-a-removed-object-is-caught
# WMBT: wmbt:migrate-projection-authority:C004
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: THE BAR — a committed projection with one document deliberately removed must make the cutover's projection criterion report UNMET and name the missing uid. Today byte-identity and self-canonicality both pass on the truncated tree and the criterion reports MET. Refs #2042.
"""A removed object must fail the check (C004-UNIT-001).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C004

This is the acceptance #2042 is judged on, and it is stated as a bar rather than a
behaviour on purpose: *a projection with an object deliberately removed must fail.*
A check that passes here is the same non-test built in a new place, and this
workstream has already shipped two of those.

Every check the cutover has compares the projection to itself, or to a projection of
the same snapshot it came from — byte-identity proves the writer is deterministic,
self-canonicality proves the serializer is stable. A comparison whose two sides share
a parent cannot detect a defect in that parent, and neither side has any opinion about
what is ABSENT.

RED: the criterion reports MET on a projection provably missing an object the store
still holds. The lab (`docs/spikes/labs/2042-projection-coverage/truncation.py`)
measures exactly this, and stays afterwards as the regression check with the sign of
its verdict flipped.
"""
from __future__ import annotations

from atdd.state import cutover
from atdd.state.projection import PROJECTION_SUFFIX

from ._coverage_helpers import (
    committed_filenames, new_repo, project_and_commit, remove_document, seed,
)


def test_a_projection_missing_an_object_reports_unmet(tmp_path) -> None:
    """The criterion refuses a truncated projection and names what is gone."""
    root = new_repo(tmp_path / "checkout")
    minted = seed(root, [("alpha-item", "PLANNED"), ("beta-item", "RED"), ("gamma-item", "GREEN")])
    out = project_and_commit(root)

    assert len(committed_filenames(root)) == len(minted), "the given is a complete projection"
    assert cutover.check(root, projection_dir=out).criteria[0].met, (
        "the intact projection must pass before removing anything, or this acceptance "
        "proves nothing about the removal"
    )

    victim_uid = minted["beta-item"]
    remove_document(root, f"{victim_uid}{PROJECTION_SUFFIX}")

    criterion = cutover.check(root, projection_dir=out).criteria[0]

    assert not criterion.met, (
        "the cutover certified a projection missing an object the store still holds. "
        "Byte-identity and self-canonicality both pass here — they compare the projection "
        "to itself — so nothing in the chain ever notices the absence"
    )
    assert any(victim_uid in blocker for blocker in criterion.blockers), (
        f"the refusal must name the missing uid {victim_uid}; an operator cannot act on "
        f"'coverage failed'. Got: {criterion.blockers}"
    )
