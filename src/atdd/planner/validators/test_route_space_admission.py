# URN: component:plan:train-interlocking:RouteSpaceAdmission:backend:tests
# Runtime: python
# Purpose: Planner validators for route-space admission + category assessment (#1554).
"""Route-space admission and category assessment validators (issue #1554).

Two ``bind_rule``-anchored validators:

  * ``planner.train.route-space-admission`` — every registered train is targeted
    by exactly one registered interlocking route OR declares a typed single-route
    assessment. Absence of a route no longer implies ``direct``.
  * ``planner.train.route-category-assessment`` — every category is covered by
    routes or by a typed not-applicable; ``nominal`` always requires routes.

**Every emittable status has a fault-injection test.** A clean-baseline assertion
on a rule that cannot emit passes forever, so each ``_assert_baseline_clean`` here
is paired with faults that drive the rule through each of its outcomes, and every
emitted evidence dict is proven a subset of the node's declared
``failure_evidence``.

The admission rule is repo-level (train registry x route registry), so its faults
are injected by materializing small on-disk repos under ``tmp_path`` rather than
by mutating a model — the rule's whole job is to notice a train the route
registry never mentions, which only exists as a property of a tree.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner.interlocking import load_interlocking, route_space
from atdd.planner.interlocking.discovery import iter_interlocking_paths
from atdd.planner.interlocking.models import (
    CategoryAssessment,
    Entrypoint,
    Fragment,
    Guard,
    Lifeline,
    Message,
    Payload,
    Projection,
    Residual,
    Route,
    RouteResolution,
    Source,
    TrainInterlocking,
)

pytestmark = [pytest.mark.platform]

_NODES_DIR = "src/atdd/planner/conventions/nodes"

_ADMISSION = "planner.train.route-space-admission"
_ASSESSMENT = "planner.train.route-category-assessment"


# ---------------------------------------------------------------------------
# evidence contract helpers
# ---------------------------------------------------------------------------
def _declared_failure_evidence(rule_id: str) -> set:
    node = find_repo_root() / _NODES_DIR / f"{rule_id}.convention.yaml"
    doc = yaml.safe_load(node.read_text(encoding="utf-8"))
    return set((doc.get("validation") or {}).get("failure_evidence") or [])


def _assert_evidence_shaped(rule_id: str, evidence: List[dict], status: str) -> None:
    """The fault was caught, emitted the expected status, and is evidence-shaped."""
    declared = _declared_failure_evidence(rule_id)
    assert evidence, f"{rule_id}: expected fault {status!r} to be caught, got nothing"
    statuses = {e.get("admission_status") or e.get("assessment_status") for e in evidence}
    assert status in statuses, f"{rule_id}: expected status {status!r}, got {statuses}"
    for ev in evidence:
        assert set(ev).issubset(declared), (
            f"{rule_id}: emitted evidence {set(ev)} not subset of declared {declared}"
        )


# ---------------------------------------------------------------------------
# on-disk repo builder for the repo-level admission rule
# ---------------------------------------------------------------------------
def _write_train(root: Path, rel: str, train_id: str, route_space_block=None) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    doc: Dict[str, Any] = {
        "train_id": train_id,
        "title": f"Train {train_id}",
        "description": f"Linear train {train_id} for route-space tests.",
        "category": "nominal",
        "themes": ["commons"],
        "participants": ["wagon:a"],
        "sequence": [{"step": 1, "intent": "do the thing", "from": "wagon:a",
                      "to": "wagon:b", "artifact": "commons:thing"}],
    }
    if route_space_block is not None:
        doc["route_space"] = route_space_block
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _write_repo(root: Path, trains: List[dict], routes: List[dict]) -> None:
    """Materialize plan/_trains.yaml + per-train docs + one interlocking.

    ``trains`` entries: {train_id, rel, route_space?}. ``routes`` entries:
    {route_id, train_id, rel}. Routes may live in a second interlocking by
    passing ``interlocking`` on the route.
    """
    plan = root / "plan"
    (plan / "_trains").mkdir(parents=True, exist_ok=True)

    bucket = []
    for t in trains:
        _write_train(root, t["rel"], t["train_id"], t.get("route_space"))
        bucket.append({"train_id": t["train_id"], "description": "d",
                       "path": t["rel"], "category": "nominal", "wagons": []})
    (plan / "_trains.yaml").write_text(
        yaml.safe_dump({"trains": {"0-commons": {"00-commons-nominal": bucket}}}),
        encoding="utf-8")

    home = plan / "_trains" / "_interlockings"
    home.mkdir(parents=True, exist_ok=True)
    by_il: Dict[str, list] = {}
    for r in routes:
        by_il.setdefault(r.get("interlocking", "interlocking:demo"), []).append(r)
    for iid, rs in by_il.items():
        name = iid.split(":", 1)[1]
        (home / f"{name}.yaml").write_text(yaml.safe_dump({
            "interlocking_id": iid,
            "routes": [{"route_id": r["route_id"], "category": "nominal",
                        "train_id": r["train_id"], "train_path": r["rel"]} for r in rs],
        }), encoding="utf-8")
    (plan / "_trains" / "_interlockings.yaml").write_text(
        yaml.safe_dump({"version": "1.0", "interlockings": [
            {"interlocking_id": iid, "path": f"plan/_trains/_interlockings/"
             f"{iid.split(':', 1)[1]}.yaml", "theme": "commons", "status": "draft"}
            for iid in by_il]}), encoding="utf-8")


_ONE_TRAIN = [{"train_id": "train:demo:alpha", "rel": "plan/_trains/demo/alpha.yaml"}]
_ONE_ROUTE = [{"route_id": "nominal", "train_id": "train:demo:alpha",
               "rel": "plan/_trains/demo/alpha.yaml"}]


# ---------------------------------------------------------------------------
# rule 1: route-space admission — clean baseline
# ---------------------------------------------------------------------------
def test_every_train_is_route_targeted_or_typed_single_route() -> None:
    """Every registered train in THIS repo is admitted to the route space."""
    rule = bind_rule(_ADMISSION)
    assert rule.rule_id == _ADMISSION
    root = find_repo_root()
    violations = route_space.route_space_admission_violations(root)
    assert violations == [], f"{_ADMISSION} violated: {violations}"


def test_admission_baseline_is_not_vacuous() -> None:
    """Guard the clean baseline: the repo really does register trains and routes.

    Without this, ``route_space_admission_violations`` returning ``[]`` because it
    found NOTHING would read exactly like compliance — the same silence-as-
    assertion failure #1554 exists to eliminate.
    """
    root = find_repo_root()
    trains = route_space.registered_trains(root)
    targets = route_space.route_targets(root)
    assert len(trains) >= 10, f"expected a populated train registry, got {len(trains)}"
    assert len(targets) >= 5, f"expected a populated route registry, got {len(targets)}"


# ---------------------------------------------------------------------------
# rule 1: fault injection — one per emittable status
# ---------------------------------------------------------------------------
def test_unrouted_and_undeclared_train_is_caught(tmp_path: Path) -> None:
    """THE headline fault: a train no route targets and which declares nothing.

    This is the case that was previously invisible — silence read as a positive
    assertion that route analysis had concluded ``direct``.
    """
    _write_repo(tmp_path, _ONE_TRAIN, routes=[])
    ev = route_space.route_space_admission_violations(tmp_path)
    _assert_evidence_shaped(_ADMISSION, ev, "unrouted-and-undeclared")


def test_typed_single_route_declaration_admits_an_unrouted_train(tmp_path: Path) -> None:
    """The same unrouted train is CLEAN once it declares a typed assessment."""
    trains = [{**_ONE_TRAIN[0], "route_space": {
        "classification": "single-route", "basis": "sole-terminal-outcome"}}]
    _write_repo(tmp_path, trains, routes=[])
    assert route_space.route_space_admission_violations(tmp_path) == []


def test_route_targeted_train_is_admitted(tmp_path: Path) -> None:
    """A train targeted by exactly one route needs no declaration."""
    _write_repo(tmp_path, _ONE_TRAIN, _ONE_ROUTE)
    assert route_space.route_space_admission_violations(tmp_path) == []


def test_multiply_routed_train_is_caught(tmp_path: Path) -> None:
    """Two routes selecting one train make the route -> train edge ambiguous."""
    routes = _ONE_ROUTE + [{"route_id": "second", "train_id": "train:demo:alpha",
                            "rel": "plan/_trains/demo/alpha.yaml",
                            "interlocking": "interlocking:other"}]
    _write_repo(tmp_path, _ONE_TRAIN, routes)
    ev = route_space.route_space_admission_violations(tmp_path)
    _assert_evidence_shaped(_ADMISSION, ev, "multiply-routed")


def test_route_targeted_and_declared_is_caught(tmp_path: Path) -> None:
    """Route-targeted AND self-declared = two sources of truth for one fact."""
    trains = [{**_ONE_TRAIN[0], "route_space": {
        "classification": "single-route", "basis": "sole-terminal-outcome"}}]
    _write_repo(tmp_path, trains, _ONE_ROUTE)
    ev = route_space.route_space_admission_violations(tmp_path)
    _assert_evidence_shaped(_ADMISSION, ev, "route-targeted-and-declared")


def test_self_declared_route_targeting_is_caught(tmp_path: Path) -> None:
    """A train may not declare itself route-targeted — that is DERIVED."""
    trains = [{**_ONE_TRAIN[0], "route_space": {
        "classification": "route-targeted", "basis": "sole-terminal-outcome"}}]
    _write_repo(tmp_path, trains, routes=[])
    ev = route_space.route_space_admission_violations(tmp_path)
    _assert_evidence_shaped(_ADMISSION, ev, "invalid-classification")


def test_prose_basis_is_rejected(tmp_path: Path) -> None:
    """A free-text basis is refused — the vocabulary is CLOSED.

    This is the anti-erosion property from #1554 decision 2: a prose reason gets
    copy-pasted until every train carries one, so it is never a valid basis no
    matter how plausible the sentence.
    """
    trains = [{**_ONE_TRAIN[0], "route_space": {
        "classification": "single-route",
        "basis": "this train genuinely only has one sensible path"}}]
    _write_repo(tmp_path, trains, routes=[])
    ev = route_space.route_space_admission_violations(tmp_path)
    _assert_evidence_shaped(_ADMISSION, ev, "invalid-basis")


def test_transitional_basis_without_retirer_is_caught(tmp_path: Path) -> None:
    """``not-yet-assessed`` without ``retires_with`` is an unowned obligation."""
    trains = [{**_ONE_TRAIN[0], "route_space": {
        "classification": "single-route", "basis": "not-yet-assessed"}}]
    _write_repo(tmp_path, trains, routes=[])
    ev = route_space.route_space_admission_violations(tmp_path)
    _assert_evidence_shaped(_ADMISSION, ev, "transitional-without-retirer")


def test_admission_reads_the_route_registry_not_source_interlocking(tmp_path: Path) -> None:
    """#1554 constraint 1: ``source_interlocking`` is NOT an authority.

    A train carrying a ``source_interlocking`` back-reference but targeted by no
    route is still unrouted. Honouring that optional, denormalized field would
    duplicate the authoritative route -> train edge — the schema says it is
    'pure traceability ... NOT a second source of truth'.
    """
    _write_repo(tmp_path, _ONE_TRAIN, routes=[])
    train = tmp_path / "plan/_trains/demo/alpha.yaml"
    doc = yaml.safe_load(train.read_text())
    doc["source_interlocking"] = {"interlocking_id": "interlocking:demo",
                                  "route_id": "nominal"}
    train.write_text(yaml.safe_dump(doc), encoding="utf-8")
    ev = route_space.route_space_admission_violations(tmp_path)
    _assert_evidence_shaped(_ADMISSION, ev, "unrouted-and-undeclared")


# ---------------------------------------------------------------------------
# rule 2: category assessment — model builder
# ---------------------------------------------------------------------------
def _model(routes, assessments=(), residuals=None) -> TrainInterlocking:
    """A minimal interlocking carrying the given routes/assessments/residuals."""
    if residuals is None:
        residuals = (Residual(id="residual:known", kind="structural", reason="r",
                              acceptance_ref="acc:x", validator_ref="t::t"),)
    return TrainInterlocking(
        schema_version="1.0.0", interlocking_id="interlocking:demo", title="Demo",
        theme="demo", status="draft",
        source=Source(path="plan/_trains/_interlockings/demo.yaml", content_digest="x"),
        entrypoint=Entrypoint(exposed=True, actions=("act",), reason=None),
        route_resolution=RouteResolution(strategy="first_priority"),
        lifelines=(Lifeline("wagon:a"), Lifeline("wagon:b")),
        messages=(Message(id="m1", kind="boundary", sender="wagon:a",
                          recipient="wagon:b", intent="do",
                          payload=Payload(contract="demo:thing"), feature_refs=()),),
        fragments=(Fragment(id="f1", kind="alt", guards=(Guard("g0", "x == true"),),
                            acceptance_refs=("acc:demo",)),),
        residuals=tuple(residuals),
        routes=tuple(routes),
        category_assessments=tuple(assessments),
    )


def _route(route_id: str, category: str) -> Route:
    return Route(route_id=route_id, category=category, priority=1, guard_ref="g0",
                 train_id=f"train:demo:{route_id}",
                 train_path=f"plan/_trains/demo/{route_id}.yaml",
                 projection=Projection(expected_sequence_digest="D"))


_ALL_CATEGORIES = tuple(_route(c, c) for c in route_space.CATEGORIES)


# ---------------------------------------------------------------------------
# rule 2: clean baseline + fault injection
# ---------------------------------------------------------------------------
def test_every_category_is_assessed_or_typed_not_applicable() -> None:
    """Every interlocking in THIS repo assesses every category."""
    rule = bind_rule(_ASSESSMENT)
    assert rule.rule_id == _ASSESSMENT
    root = find_repo_root()
    interlockings = [load_interlocking(p) for p in iter_interlocking_paths(root)]
    assert interlockings, "expected the repo to declare interlockings"
    for il in interlockings:
        ev = route_space.category_assessment_violations(il, root)
        assert ev == [], f"{_ASSESSMENT} violated by {il.interlocking_id}: {ev}"


def test_fully_routed_interlocking_is_clean() -> None:
    """Routes in all four categories need no assessment at all."""
    assert route_space.category_assessment_violations(_model(_ALL_CATEGORIES)) == []


def test_unassessed_category_is_caught() -> None:
    """A category with neither routes nor an assessment is caught."""
    routes = tuple(r for r in _ALL_CATEGORIES if r.category != "error")
    ev = route_space.category_assessment_violations(_model(routes))
    _assert_evidence_shaped(_ASSESSMENT, ev, "unassessed")


def test_token_alternate_does_not_satisfy_error_and_exception() -> None:
    """THE gaming fault #1554 names: a token alternate must not buy silence.

    An interlocking with nominal + one alternate and NOTHING said about error or
    exception is caught twice — once per unassessed category. Under an
    'at least one non-nominal route' floor this passed.
    """
    routes = (_route("nominal", "nominal"), _route("token", "alternate"))
    ev = route_space.category_assessment_violations(_model(routes))
    unassessed = {e["category"] for e in ev if e["assessment_status"] == "unassessed"}
    assert unassessed == {"error", "exception"}, (
        f"a token alternate must not discharge error+exception; got {unassessed}")
    _assert_evidence_shaped(_ASSESSMENT, ev, "unassessed")


def test_nominal_can_never_be_discharged() -> None:
    """``nominal`` is the executed path: an assessment never satisfies it."""
    routes = tuple(r for r in _ALL_CATEGORIES if r.category != "nominal")
    assessments = (CategoryAssessment(category="nominal", basis="outcome-cannot-arise"),)
    ev = route_space.category_assessment_violations(_model(routes, assessments))
    _assert_evidence_shaped(_ASSESSMENT, ev, "nominal-unrouted")


def test_residual_discharge_satisfies_a_category() -> None:
    """A category discharged through a DECLARED residual is clean."""
    routes = tuple(r for r in _ALL_CATEGORIES if r.category != "error")
    assessments = (CategoryAssessment(category="error", basis="discharged-by-residual",
                                      residual_ref="residual:known"),)
    assert route_space.category_assessment_violations(_model(routes, assessments)) == []


def test_discharge_through_undeclared_residual_is_caught() -> None:
    """Discharging through a residual that does not exist is caught.

    This is what keeps ``discharged-by-residual`` from being a free-text hatch by
    another name: the named residual must actually be declared, and every declared
    residual must itself carry a reason, acceptance_ref and validator_ref.
    """
    routes = tuple(r for r in _ALL_CATEGORIES if r.category != "error")
    assessments = (CategoryAssessment(category="error", basis="discharged-by-residual",
                                      residual_ref="residual:imaginary"),)
    ev = route_space.category_assessment_violations(_model(routes, assessments))
    _assert_evidence_shaped(_ASSESSMENT, ev, "discharge-residual-undeclared")


def test_discharge_without_residual_ref_is_caught() -> None:
    routes = tuple(r for r in _ALL_CATEGORIES if r.category != "error")
    assessments = (CategoryAssessment(category="error", basis="discharged-by-residual"),)
    ev = route_space.category_assessment_violations(_model(routes, assessments))
    _assert_evidence_shaped(_ASSESSMENT, ev, "discharge-without-residual")


def test_routed_and_discharged_is_a_contradiction() -> None:
    """A stale not-applicable cannot outlive the gap it described."""
    assessments = (CategoryAssessment(category="error", basis="outcome-cannot-arise"),)
    ev = route_space.category_assessment_violations(_model(_ALL_CATEGORIES, assessments))
    _assert_evidence_shaped(_ASSESSMENT, ev, "routed-and-discharged")


def test_prose_category_basis_is_rejected() -> None:
    """A free-text category basis is refused — the vocabulary is CLOSED."""
    routes = tuple(r for r in _ALL_CATEGORIES if r.category != "error")
    assessments = (CategoryAssessment(category="error",
                                      basis="we looked and it seemed fine"),)
    ev = route_space.category_assessment_violations(_model(routes, assessments))
    _assert_evidence_shaped(_ASSESSMENT, ev, "invalid-basis")


def test_transitional_category_without_retirer_is_caught() -> None:
    routes = tuple(r for r in _ALL_CATEGORIES if r.category != "error")
    assessments = (CategoryAssessment(category="error", basis="not-yet-assessed"),)
    ev = route_space.category_assessment_violations(_model(routes, assessments))
    _assert_evidence_shaped(_ASSESSMENT, ev, "transitional-without-retirer")


# ---------------------------------------------------------------------------
# anti-erosion: the transitional basis is an inventory, not a hiding place
# ---------------------------------------------------------------------------
#: Subjects carrying ``not-yet-assessed`` at the time #1554 landed. Adding a
#: subject here must be a deliberate, reviewed edit — that is the whole point.
#: Shrinking it is always allowed; #1549 retires these.
_EXPECTED_TRANSITIONAL_TRAINS = {
    "train:issue-lifecycle:drive-state-machine",
    "train:issue-lifecycle:record-agent-session-identity",
    "train:self-compliance:validate-lifecycle",
    "train:substrate:admit-packages",
    "train:substrate:author-artifacts",
    "train:substrate:bind-runtime",
}
_EXPECTED_TRANSITIONAL_CATEGORIES = {
    ("interlocking:enforce-extension-conventions", "error"),
}


def test_transitional_basis_inventory_does_not_grow() -> None:
    """``not-yet-assessed`` is a recorded, shrinking inventory — never a hatch.

    A closed vocabulary stops prose from eroding the gate, but a transitional
    enum value could still erode by ACCUMULATION. Pinning the exact inventory
    makes adding one a visible, reviewed decision instead of a quiet default,
    which is the same device as the recorded ratchet baseline this repo already
    uses for pre-existing failures.
    """
    root = find_repo_root()

    actual_trains = set()
    for entry in route_space.registered_trains(root):
        doc = yaml.safe_load((root / entry["path"]).read_text(encoding="utf-8")) or {}
        block = doc.get("route_space") or {}
        if block.get("basis") == "not-yet-assessed":
            actual_trains.add(entry["train_id"])

    actual_categories = set()
    for path in iter_interlocking_paths(root):
        il = load_interlocking(path)
        for ca in il.category_assessments:
            if ca.basis == "not-yet-assessed":
                actual_categories.add((il.interlocking_id, ca.category))

    new_trains = actual_trains - _EXPECTED_TRANSITIONAL_TRAINS
    new_categories = actual_categories - _EXPECTED_TRANSITIONAL_CATEGORIES
    assert not new_trains, (
        f"new transitional trains {sorted(new_trains)} — `not-yet-assessed` is a "
        f"recorded inventory retired by #1549, not a default. Either classify the "
        f"train properly or add it here deliberately.")
    assert not new_categories, (
        f"new transitional categories {sorted(new_categories)} — assess the "
        f"category or add it here deliberately.")

    # Every transitional subject names the issue that retires it.
    for entry in route_space.registered_trains(root):
        doc = yaml.safe_load((root / entry["path"]).read_text(encoding="utf-8")) or {}
        block = doc.get("route_space") or {}
        if block.get("basis") == "not-yet-assessed":
            assert block.get("retires_with"), f"{entry['train_id']} names no retirer"
