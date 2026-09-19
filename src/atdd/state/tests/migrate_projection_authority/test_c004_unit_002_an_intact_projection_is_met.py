# URN: test:migrate-projection-authority:migrate-store-projection:C004-UNIT-002-an-intact-projection-is-met
# Acceptance: acc:migrate-projection-authority:C004-UNIT-002-an-intact-projection-is-met
# WMBT: wmbt:migrate-projection-authority:C004
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The coverage check must DISCRIMINATE: an intact committed projection reports MET with no missing and no unexpected uid, so the refusal in C004-UNIT-001 is evidence about that projection rather than about the check. Refs #2042.
"""The check must discriminate, not merely refuse (C004-UNIT-002).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C004

A coverage check that refuses every projection would satisfy the bar in C004-UNIT-001
and be worthless. This is the other half of that pair, and the pair is the point: the
first says the check can fail, this says it can pass, and only together do they say it
*discriminates*.

It also pins the shape of the passing verdict — an empty `missing` AND an empty
`unexpected` — so a future implementation cannot satisfy this by reporting MET while
quietly computing nothing.
"""
from __future__ import annotations

from atdd.state import cutover

from ._coverage_helpers import (
    committed_filenames, new_repo, project_and_commit, require, seed,
)


def _store(root):
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    return StateStore(connect(init_state_store(start=root)))


def test_an_intact_projection_is_met_with_an_empty_residual(tmp_path) -> None:
    """A complete projection passes, and the report says nothing is missing or extra."""
    root = new_repo(tmp_path / "checkout")
    minted = seed(root, [("alpha-item", "PLANNED"), ("beta-item", "SMOKE")])
    out = project_and_commit(root)

    criterion = cutover.check(root, projection_dir=out).criteria[0]
    assert criterion.met, f"an intact projection must pass; blockers: {criterion.blockers}"

    check_coverage = require("check_coverage")
    projectable_uids = require("projectable_uids")
    store = _store(root)
    committed = {name[: -len(".yaml")] for name in committed_filenames(root)}
    report = check_coverage(committed, store)

    assert report.ok
    assert not report.missing, f"nothing should be missing, got {report.missing}"
    assert not report.unexpected, f"nothing should be unexpected, got {report.unexpected}"
    assert set(minted.values()) == projectable_uids(store), (
        "the obligation must be exactly the work items the store holds in a live phase"
    )
