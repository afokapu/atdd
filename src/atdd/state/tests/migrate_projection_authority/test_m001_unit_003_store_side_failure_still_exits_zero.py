# URN: test:migrate-projection-authority:compare-shadow-projection:M001-UNIT-003-store-side-failure-still-exits-zero
# Acceptance: acc:migrate-projection-authority:M001-UNIT-003-store-side-failure-still-exits-zero
# WMBT: wmbt:migrate-projection-authority:M001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A store whose documents cannot be projected must be REPORTED, not raised: the non-blocking exit code is the invariant on every path, including the store side computed before the per-source loop. Refs #2023.
"""A store-side projection failure still exits zero (M001-UNIT-003).

wagon: migrate-projection-authority | feature: compare-shadow-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:M001

:data:`shadow.SHADOW_EXIT_CODE` is declared as the invariant, "stated as a constant so the CLI, the
workflow and the tests all read the same number and none of them can drift from it (M001)". The
constant cannot drift. The *exception path never consults it*.

``compare`` computes ``ours = build_documents(store)`` at the top — before the per-source loop and
outside any handler — so a document that fails ``assert_deterministic`` escapes as a traceback and
the command exits 1, against a docstring on that very function which promises it "never raises to
gate". The report already models this outcome: ``unavailable`` exists for "sources that could not be
compared at all — reported, not fatal". The store side is the one failure that cannot reach it.

This is not hypothetical. On the toolkit's own repo, 195 of 1265 objects carry an absolute host path
in ``worktree_path`` and ``atdd state shadow`` exits 1 today — while CI renders it as a green job
with an empty drift report, because the step has no ``pipefail``, the traceback goes to stderr which
``tee`` never captures, and the summary's ``|| echo '(no report produced)'`` fallback does not fire
on an empty-but-present file. A measurement that dies silently and reports clean is worse than one
that reports nothing. Refs #2023 / #1434.
"""
from __future__ import annotations

import pytest

from atdd.state import shadow
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import NondeterministicProjectionError

from ._helpers import UID_A, control_root, memory_store

#: The shape of the real defect: a per-machine absolute path in the object's data bag, which
#: `build_document` carries through verbatim and `assert_deterministic` then refuses (I1).
_UNPROJECTABLE = {
    "slug": "alpha",
    "owner_actor": "dev-a",
    "state": "ACTIVE",
    "wmbts": [],
    "worktree_path": "/Users/someone/Github/atdd/worktrees/feat-alpha",
}


def _run(tmp_path):
    root = control_root(tmp_path / "repo")
    projection = root / ".atdd" / "state" / "projection"
    projection.mkdir(parents=True, exist_ok=True)
    with memory_store() as (_conn, store):
        store.objects.upsert(UID_A, WORK_ITEM_KIND, state="PLANNED", data=dict(_UNPROJECTABLE))
        return shadow.compare(
            store, root=root, projection_dir=projection, sources=[shadow.SOURCE_COMMITTED],
        )


def test_m001_unit_003_store_side_failure_does_not_raise(tmp_path) -> None:
    """compare() honours its own "never raises to gate" when the store cannot be projected."""
    try:
        report = _run(tmp_path)
    except NondeterministicProjectionError as exc:
        pytest.fail(
            "compare() raised instead of reporting: "
            f"{exc}. Its docstring promises it 'never raises to gate', and SHADOW_EXIT_CODE is "
            "declared the invariant — but build_documents() runs above the per-source loop and "
            "outside any handler, so the constant is never consulted on this path."
        )
    assert report.exit_code == shadow.SHADOW_EXIT_CODE


def test_m001_unit_003_the_failure_is_reported_as_an_unavailable_source(tmp_path) -> None:
    """The operator is told the run died — an empty report reads exactly like zero drift."""
    report = _run(tmp_path)
    assert report.unavailable, (
        "the store-side failure left no trace in the report; `unavailable` exists for precisely "
        "'sources that could not be compared at all'"
    )
    assert shadow.SOURCE_STORE in report.unavailable, (
        f"expected the store side keyed as {shadow.SOURCE_STORE!r}; got {sorted(report.unavailable)}"
    )
    rendered = report.render()
    assert "worktree_path" in rendered, (
        f"the rendered report does not name the offending field:\n{rendered}"
    )


def test_m001_unit_003_a_dead_run_is_distinguishable_from_a_clean_one(tmp_path) -> None:
    """The whole defect in one assertion: 'it crashed' must not render as 'no drift'."""
    report = _run(tmp_path)
    assert report.render().strip(), "a dead run produced an empty report"
    assert "no drift" not in report.render(), (
        "a run that could not project the store reported 'no drift' — which is what a clean run "
        "reports, and the operator cannot tell the two apart"
    )
