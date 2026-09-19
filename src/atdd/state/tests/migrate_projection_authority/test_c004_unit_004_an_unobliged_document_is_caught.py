# URN: test:migrate-projection-authority:migrate-store-projection:C004-UNIT-004-an-unobliged-document-is-caught
# Acceptance: acc:migrate-projection-authority:C004-UNIT-004-an-unobliged-document-is-caught
# WMBT: wmbt:migrate-projection-authority:C004
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Coverage is a set comparison in BOTH directions — a committed document for a uid the store does not oblige makes the criterion UNMET, and the blocker distinguishes an unobliged document from a missing one. Equal counts with different members is exactly what a count check cannot see. Refs #2042.
"""Coverage runs both ways (C004-UNIT-004).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C004

The obvious coverage check counts: `len(committed) == len(obliged)`. It is wrong, and the
case that breaks it is the realistic one — a document removed and an unrelated document
added, which leaves the counts equal and the projection wrong in two directions at once.

So this asserts the other direction: a document the store does not oblige is a defect on
its own. Either the store lost an object the projection still describes, or the projection
carries a uid that never existed; both are the shared truth disagreeing with the store, and
a set comparison catches both while a count catches neither.

The second assertion is about the operator, not the algorithm. "Missing" and "unexpected"
are different faults with different remedies — one means re-project, the other means find
out who wrote that file — and a blocker that flattens them into "coverage failed" sends the
operator looking in the wrong place.
"""
from __future__ import annotations

from atdd.state import cutover
from atdd.state.projection import PROJECTION_SUFFIX

from ._coverage_helpers import (
    commit_all, committed_filenames, new_repo, project_and_commit, require, seed,
)

_INTRUDER = "wi_01HF7YAT00M78607F000000099"


def _store(root):
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    return StateStore(connect(init_state_store(start=root)))


def test_a_document_the_store_does_not_oblige_reports_unmet(tmp_path) -> None:
    """An extra document is a coverage defect, and is named as extra rather than missing."""
    root = new_repo(tmp_path / "checkout")
    minted = seed(root, [("alpha-item", "PLANNED"), ("beta-item", "RED")])
    out = project_and_commit(root)

    # A document for a uid no object in the store obliges. Copying a real one keeps it
    # schema-valid, so the ONLY thing wrong with the projection is its population.
    donor = sorted(committed_filenames(root))[0]
    body = (out / donor).read_text(encoding="utf-8")
    real_uid = donor[: -len(PROJECTION_SUFFIX)]
    (out / f"{_INTRUDER}{PROJECTION_SUFFIX}").write_text(
        body.replace(real_uid, _INTRUDER), encoding="utf-8",
    )
    commit_all(root, "a document the store does not oblige")

    criterion = cutover.check(root, projection_dir=out).criteria[0]
    assert not criterion.met, (
        "the cutover certified a projection carrying a document for a uid the store does "
        "not hold — the shared truth describes an object that does not exist"
    )
    assert any(_INTRUDER in blocker for blocker in criterion.blockers), (
        f"the refusal must name the unobliged uid. Got: {criterion.blockers}"
    )

    check_coverage = require("check_coverage")
    store = _store(root)
    committed = {name[: -len(PROJECTION_SUFFIX)] for name in committed_filenames(root)}
    report = check_coverage(committed, store)
    assert _INTRUDER in report.unexpected, "it is UNEXPECTED, not MISSING"
    assert not report.missing, (
        f"nothing is missing here; reporting {report.missing} would send the operator to "
        "re-project when the remedy is to find out who wrote that file"
    )
    assert set(minted.values()) <= committed, "the real documents are all still there"
