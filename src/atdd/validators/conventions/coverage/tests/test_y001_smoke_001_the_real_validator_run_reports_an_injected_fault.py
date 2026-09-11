# URN: test:author-plan-substrate:interlocking-coverage-projections-are-live:Y001-SMOKE-001-the-real-validator-run-reports-an-injected-fault
# Acceptance: acc:author-plan-substrate:Y001-SMOKE-001-the-real-validator-run-reports-an-injected-fault
# WMBT: wmbt:author-plan-substrate:Y001
# Phase: SMOKE
# Layer: integration
"""Y001-SMOKE-001 — the shipped projection dispatch, over an injected fault (#1547).

The UNIT test calls `_interlocking_wmbt_surface_or_residual` and
`_interlocking_guard_coverage` directly. This one goes through
`_projection_covers_source` — the function the convention layer actually
dispatches to, selected by the same `variant` string the convention YAML carries.

That matters here specifically. The defect was not a wrong answer; it was a
projection that could produce no answer at all, wired into a dispatch table that
reported its silence as coverage. Asserting on the private helpers proves the
helpers work. Asserting through `_PROJECTION_VARIANTS` proves the thing the
convention layer reaches is the repaired one.
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
    if spec is None or spec.loader is None:  # pragma: no cover — a missing fixture file
        raise RuntimeError(f"interlocking fixtures are not importable at {path}")
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

from atdd.validators.conventions.coverage import archetype  # noqa: E402

pytestmark = [pytest.mark.platform]

WMBT_VARIANT = "planner_train_interlocking_wmbt_surface_or_residual"
GUARD_VARIANT = "planner_train_interlocking_guard_coverage"


class _Graph:
    def __init__(self, root: pathlib.Path) -> None:
        self.root = root


def _project(root: pathlib.Path, variant: str):
    return archetype._projection_covers_source(_Graph(root), {"variant": variant})


def test_both_variants_are_registered_in_the_dispatch_table() -> None:
    """If a variant is missing the convention silently checks nothing."""
    assert WMBT_VARIANT in archetype._PROJECTION_VARIANTS
    assert GUARD_VARIANT in archetype._PROJECTION_VARIANTS


def test_the_dispatched_wmbt_projection_reports_an_injected_fault(tmp_path) -> None:
    """THE POINT: through the real dispatch, an unsurfaced obligation is reported."""
    doc = copy.deepcopy(interlocking_doc())
    doc["invariants"][0]["expression"] = "   "
    write_tree(tmp_path, doc)
    out = _project(tmp_path, WMBT_VARIANT)
    assert out, (
        "the dispatched projection reported nothing for an invariant that "
        "asserts nothing — it is inert again"
    )
    assert out[0]["coverage_status"] == "unsurfaced"


def test_the_dispatched_guard_projection_reports_an_injected_fault(tmp_path) -> None:
    """Same, for the sibling branch."""
    doc = copy.deepcopy(interlocking_doc())
    dropped = doc["routes"].pop(0)
    write_tree(tmp_path, doc)
    out = _project(tmp_path, GUARD_VARIANT)
    assert any(v["guard_id"] == dropped["guard_ref"] for v in out), (
        f"the dispatched projection did not report unrouted {dropped['guard_ref']}: {out}"
    )


def test_a_clean_tree_dispatches_to_silence(tmp_path) -> None:
    """The projections must not simply always fire — otherwise the repository
    itself would go red and the check would be worthless in the other direction."""
    write_tree(tmp_path)
    assert _project(tmp_path, WMBT_VARIANT) == []
    assert _project(tmp_path, GUARD_VARIANT) == []


def test_this_repository_is_clean_under_the_now_live_projections() -> None:
    """The projections went from inert to live; this records what they say about
    the real plan, so a future violation is a change rather than a surprise."""
    root = pathlib.Path(__file__).resolve().parents[6]
    assert (root / "plan").is_dir(), f"expected a plan/ under {root}"
    assert _project(root, WMBT_VARIANT) == []
    assert _project(root, GUARD_VARIANT) == []
