# URN: test:author-plan-substrate:interlocking-coverage-projections-are-live:Y001-UNIT-001-the-interlocking-projections-can-fail
# Acceptance: acc:author-plan-substrate:Y001-UNIT-001-the-interlocking-projections-can-fail
# WMBT: wmbt:author-plan-substrate:Y001
# Phase: GREEN
# Layer: backend.unit
"""Y001-UNIT-001 — fault injection per repaired branch (#1547).

Both interlocking coverage projections were provably inert.

`_interlocking_wmbt_surface_or_residual` seeded `surfaced` from `il.invariants`
and then tested every `inv.wmbt_ref` for membership in it — true by construction,
so the append was unreachable and the projection returned `[]` for any data.

`_interlocking_guard_coverage` built `{rsd.id ...}` — the `residual:` namespace —
and tested `guard_id in residual_guards` against the `guard:` namespace. Measured
on this repository's own interlockings, that intersection is empty for every file,
so the branch could never be taken.

`planner/interlocking/sanity.py` already carries the repaired versions of both,
with comments citing this issue. The archetype kept a stale second copy — which is
why a clean baseline said nothing was wrong. These projections now delegate to
sanity, so there is one implementation rather than two that agree until they don't.

**The acceptance condition here is that each branch can FAIL**, not that the
repository is clean. Every test below injects the specific fault the branch exists
to catch and asserts it is reported.
"""
from __future__ import annotations

import copy
import pathlib
import pytest


def _load_fixtures():
    """Import the planner's interlocking fixtures without touching `sys.path`.

    `tester.isolation` forbids module-level `sys.path` mutation, and it is right
    to: a test that edits the interpreter's import state leaks into every test
    that runs after it in the same process.
    """
    import importlib.util

    path = (pathlib.Path(__file__).resolve().parents[4]
            / "planner" / "interlocking" / "tests" / "_fixtures.py")
    spec = importlib.util.spec_from_file_location("_il_fixtures_for_y001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def interlocking_doc():
    """A fresh fixture document. Loaded per call rather than bound at module
    level: a module-level alias is mutable global state, which `tester.isolation`
    forbids for the same reason it forbids a `sys.path` edit — it outlives the
    test that set it."""
    return _load_fixtures().interlocking_doc()


def write_tree(root, doc=None):
    return _load_fixtures().write_tree(root, doc)

from atdd.validators.conventions.coverage.archetype import (  # noqa: E402
    _interlocking_guard_coverage,
    _interlocking_wmbt_surface_or_residual,
)


class _Graph:
    """The archetype takes anything with a `.root`."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root


def _graph(tmp_path: pathlib.Path, doc: dict | None = None) -> _Graph:
    write_tree(tmp_path, doc)
    return _Graph(tmp_path)


def test_a_clean_interlocking_reports_nothing(tmp_path) -> None:
    """The projections must not simply always fire."""
    g = _graph(tmp_path)
    assert _interlocking_wmbt_surface_or_residual(g) == []
    assert _interlocking_guard_coverage(g) == []


def test_an_invariant_that_asserts_nothing_is_unsurfaced(tmp_path) -> None:
    """FAULT 1 — the tautology. An invariant naming a WMBT but carrying no
    expression enforces nothing; the old code could never say so."""
    doc = copy.deepcopy(interlocking_doc())
    doc["invariants"][0]["expression"] = "   "
    out = _interlocking_wmbt_surface_or_residual(_graph(tmp_path, doc))
    assert out, (
        "an invariant with an empty expression was reported as surfaced — the "
        "`surfaced`-seeded-from-the-iterated-set tautology is back"
    )
    assert out[0]["coverage_status"] == "unsurfaced"
    assert out[0]["wmbt_ref"] == doc["invariants"][0]["wmbt_ref"]


def test_a_structural_residual_still_discharges_an_unsurfaced_obligation(tmp_path) -> None:
    """FAULT 1, the escape hatch — and it must work in the `wmbt:` namespace.

    This is the branch the `{rsd.id ...}` set made structurally dead: a residual
    id lives in `residual:`, a wmbt_ref in `wmbt:`, so the discharge could never
    match and the escape was unreachable.
    """
    doc = copy.deepcopy(interlocking_doc())
    ref = doc["invariants"][0]["wmbt_ref"]
    doc["invariants"][0]["expression"] = "   "
    for rsd in doc["residuals"]:
        if rsd.get("kind") == "structural":
            rsd["wmbt_refs"] = [*rsd.get("wmbt_refs", []), ref]
            break
    else:
        pytest.fail("fixture carries no structural residual to discharge with")
    assert _interlocking_wmbt_surface_or_residual(_graph(tmp_path, doc)) == [], (
        "a structural residual naming the obligation did not discharge it; the "
        "escape is dead again"
    )


def test_a_guard_with_no_route_is_uncovered(tmp_path) -> None:
    """FAULT 2 — guard coverage. Remove the route and the guard must be reported."""
    doc = copy.deepcopy(interlocking_doc())
    dropped = doc["routes"].pop(0)
    out = _interlocking_guard_coverage(_graph(tmp_path, doc))
    assert any(v["guard_id"] == dropped["guard_ref"] for v in out), (
        f"guard {dropped['guard_ref']} lost its only route and was not reported: {out}"
    )


def test_a_structural_residual_excuses_an_unrouted_guard(tmp_path) -> None:
    """FAULT 2, the escape hatch — via guard -> WMBT -> residual, the linkage
    `Residual` actually carries. `residual:` ids never matched `guard:` ids."""
    doc = copy.deepcopy(interlocking_doc())
    dropped = doc["routes"].pop(0)
    # Guards are declared inside fragments, not at the top level — the linkage
    # this branch depends on lives at `fragments[].guards[].wmbt_refs`.
    guard = next(
        g for frag in doc["fragments"] for g in frag.get("guards", [])
        if g["id"] == dropped["guard_ref"]
    )
    guard_wmbts = list(guard.get("wmbt_refs") or [])
    if not guard_wmbts:
        pytest.skip("fixture guard carries no wmbt_refs; the linkage cannot be exercised")
    for rsd in doc["residuals"]:
        if rsd.get("kind") == "structural":
            rsd["wmbt_refs"] = [*rsd.get("wmbt_refs", []), *guard_wmbts]
            break
    out = _interlocking_guard_coverage(_graph(tmp_path, doc))
    assert not any(v["guard_id"] == dropped["guard_ref"] for v in out), (
        "a structural residual discharging the guard's WMBT did not excuse it"
    )
