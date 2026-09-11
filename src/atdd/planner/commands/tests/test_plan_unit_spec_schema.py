# URN: test:atdd-plan-core:session-machine:unit-spec-schema
# Issue: #1929
# Phase: GREEN
# Layer: backend.domain
# Assertion: behavioral
"""#1929 — `atdd plan unit` validates a hand-authored spec against its schema.

Binds `planner.plan.spec-is-schema-valid` and
`planner.plan.granularity-completeness`.

The two axes under test are independent and both matter:

  STAGE  Compose checks well-formedness (is what IS here shaped right?), Ratify
         adds completeness (is everything here yet?). Getting this backwards
         breaks the drafting loop `add_unit`'s upsert exists to support.
  TIER   an honest schema RAISES, a drifted one REPORTS. Enforcing the drifted
         ones would refuse 134/188 of this repo's own features.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit,
)
from atdd.planner.commands.plan_unit_schema import (
    AUTHORABLE_KINDS, KNOWN_KINDS, REASONING_KINDS, check_unit_spec,
    project_for_schema,
)

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.plan.spec-is-schema-valid")
_LADDER_RULE = bind_rule("planner.plan.granularity-completeness")


def _wagon_spec(slug: str = "capture-audio", **over) -> dict:
    spec = {
        "wagon": slug,
        "description": f"{slug} for the spec-schema fixtures",
        "subject": "agent:planner", "context": "commute",
        "action": "captures audio", "goal": "music on the go",
        "outcome": "audio is captured",
        "produce": [{"name": "commons:audio:stream"}],
    }
    spec.update(over)
    return spec


def _ratify_ready(units) -> PlanSession:
    s = PlanSession("spec-sess", step=Step.RATIFY.value, issue_ref="my-plan")
    s.units = units
    return s


# --- Compose: well-formedness -------------------------------------------------

def test_compose_refuses_a_malformed_enforced_spec():
    """A value that is present and wrong is refused the moment it is written."""
    s = PlanSession("s", main_job="x", issue_ref="i")
    with pytest.raises(SessionGateError, match="spec-is-schema-valid"):
        s.add_unit(Unit(kind="wagon", ref="w",
                        spec=_wagon_spec(theme="Ingest Pipeline")))
    assert s.units == [], "a refused unit must not enter the session"


def test_compose_admits_an_incomplete_draft():
    """Compose is a drafting loop: missing fields are not yet a defect."""
    s = PlanSession("s", main_job="x", issue_ref="i")
    s.add_unit(Unit(kind="wagon", ref="w", spec={"wagon": "capture-audio"}))
    assert [u["ref"] for u in s.units] == ["w"]


def test_compose_refuses_an_unknown_kind():
    """A typo'd kind used to ride through Ratify and fail only at author."""
    s = PlanSession("s", main_job="x", issue_ref="i")
    with pytest.raises(SessionGateError, match="unknown plan kind"):
        s.add_unit(Unit(kind="wagonn", ref="w", spec={}))


def test_kind_conflict_outranks_a_malformed_spec():
    """The structural mistake is reported, not the fields of the wrong schema."""
    s = PlanSession("s", main_job="x", issue_ref="i")
    s.add_unit(Unit(kind="wagon", ref="w1", spec={"wagon": "capture-audio"}))
    with pytest.raises(SessionGateError, match="already exists as kind"):
        s.add_unit(Unit(kind="feature", ref="w1", spec={"a": 1}))


# --- Ratify: completeness -----------------------------------------------------

def test_ratify_refuses_an_incomplete_kept_spec(tmp_path):
    """The draft Compose admitted must be finished before the lock."""
    s = _ratify_ready([{"kind": "wagon", "ref": "w", "verdict": "keep",
                        "spec": {"wagon": "capture-audio"}}])
    with pytest.raises(SessionGateError, match="spec-is-schema-valid"):
        s.confirm(tmp_path)
    assert s.locked is False, "the gate must fail closed"


def test_ratify_locks_a_complete_kept_spec(tmp_path):
    s = _ratify_ready([{"kind": "wagon", "ref": "w", "verdict": "keep",
                        "spec": _wagon_spec()}])
    s.confirm(tmp_path)
    assert s.locked is True


def test_ratify_never_blocks_on_an_advisory_kind(tmp_path):
    """A drifted schema reports; enforcing it would refuse this repo's corpus."""
    s = _ratify_ready([
        {"kind": "wagon", "ref": "w", "verdict": "keep", "spec": _wagon_spec()},
        {"kind": "wmbt", "ref": "m", "verdict": "keep",
         "spec": {"wagon_slug": "capture-audio", "code": "E001",
                  "object_of_control": "time to capture a source occurrence"}},
    ])
    s.confirm(tmp_path)
    assert s.locked is True
    advisories = [u for u in s.units if u.get("advisories")]
    assert advisories and advisories[0]["ref"] == "m", \
        "the finding must ride on the unit so it survives compaction"


# --- the granularity ladder ---------------------------------------------------

def test_ratify_reports_the_dangling_ladder(tmp_path):
    s = _ratify_ready([{"kind": "wagon", "ref": "w", "verdict": "keep",
                        "spec": _wagon_spec()}])
    s.confirm(tmp_path)
    report = s.granularity_report()
    assert s.locked is True, "the ladder report must not block"
    assert report["reached"] == ["wagon"]
    assert report["dangling"] == ["feature", "wmbt", "acceptance"]


# --- reasoning kinds ----------------------------------------------------------

def test_a_kept_reasoning_unit_authors_nothing(tmp_path):
    """`keep-pivot-kill`: an artifact is written only after a FINAL-granularity keep."""
    s = _ratify_ready([
        {"kind": "wagon", "ref": "w", "verdict": "keep", "spec": _wagon_spec()},
        {"kind": "heuristic", "ref": "h", "verdict": "keep",
         "spec": {"note": "batch writes at the boundary"}},
    ])
    s.confirm(tmp_path)
    seen = []
    s.author(lambda kind, spec: seen.append(kind) or kind)
    assert seen == ["wagon"], "the kept heuristic must be skipped, not raised on"


def test_reasoning_and_authorable_kinds_are_disjoint_and_total():
    assert REASONING_KINDS & AUTHORABLE_KINDS == set()
    assert REASONING_KINDS | AUTHORABLE_KINDS == KNOWN_KINDS


# --- the projection -----------------------------------------------------------

def test_projection_matches_what_the_writer_would_write():
    """Compose and Author must hold the SAME document to the same schema."""
    projected = project_for_schema("wagon", _wagon_spec())
    assert projected["produce"][0]["to"] == "external", "writer default"
    assert projected["wmbt"] == {"total": 0}, "writer default"
    assert projected["consume"] == []
    # input-only keys the writer drops must not reach the schema
    wmbt = project_for_schema(
        "wmbt", {"wagon_slug": "capture-audio", "code": "E001", "lens": "functional.x"})
    assert wmbt["urn"] == "wmbt:capture-audio:E001"
    assert "wagon_slug" not in wmbt and "code" not in wmbt


def test_enforced_kinds_accept_the_repo_corpus():
    """The enforce tier is measured, not asserted — see the module docstring."""
    import yaml
    from pathlib import Path
    from atdd.coach.utils.repo import find_repo_root

    plan = Path(find_repo_root(Path(__file__))) / "plan"
    wagons = [p for p in plan.glob("*/_*.yaml") if not p.parent.name.startswith("_")]
    if not wagons:
        pytest.skip("no plan/ corpus in this checkout")
    offenders = []
    for path in wagons:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or "wagon" not in doc:
            continue
        _, findings = check_unit_spec("wagon", doc, stage="ratify")
        if findings:
            offenders.append(f"{path}: {findings[0]}")
    assert not offenders, (
        "an enforced kind must accept every artifact the repo ships, or the gate "
        "refuses the decomposition atdd itself authored:\n  " + "\n  ".join(offenders))
