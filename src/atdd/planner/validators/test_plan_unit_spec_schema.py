# URN: component:atdd-plan-core:session-machine:plan_unit_spec_schema:backend:domain
# Purpose: Enforce planner.plan.spec-is-schema-valid and
#          planner.plan.granularity-completeness (#1929) — a hand-authored plan
#          unit spec is held to its artifact schema (well-formedness at Compose,
#          completeness at Ratify), and Ratify names the granularity rungs a
#          decomposition never descended.
"""planner.plan.spec-is-schema-valid + granularity-completeness validators (#1929).

Behavioural gates, mirroring the sibling confirm-gate validators:

* a malformed spec for an ENFORCED kind must be refused at Compose, and an
  incomplete draft must NOT be (Compose is a drafting loop);
* a kept spec that would author a schema-invalid artifact must be refused at
  Ratify, leaving the session unlocked;
* an ADVISORY kind must never block, and its findings must ride on the unit;
* Ratify must report the dangling ladder without blocking.

The last check is the one that keeps the enforce tier honest: every artifact in
this repo's own ``plan/`` tree must satisfy the schema of an enforced kind, or
the gate refuses the decomposition atdd itself authored.

Rules: planner.plan.spec-is-schema-valid, planner.plan.granularity-completeness
Run:   atdd validate planner
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit, Verdict,
)
from atdd.planner.commands.plan_unit_schema import check_unit_spec
from atdd.planner.validators._plan_session_fixtures import wagon_spec

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.plan.spec-is-schema-valid")
_LADDER_RULE = bind_rule("planner.plan.granularity-completeness")
_VALIDATOR_ID = "plan_unit_spec_schema"
_LOC = "src/atdd/planner/commands/plan_session.py:PlanSession.add_unit"
_LOC_RATIFY = "src/atdd/planner/commands/plan_session.py:PlanSession.confirm"


def _violation(rule, location: str, detail: str) -> Violation:
    return Violation(rule_id=rule.rule_id, severity=rule.severity,
                     location=location, detail=detail)


def _scan_compose() -> List[Violation]:
    """Compose refuses a malformed enforced spec, and admits an incomplete draft."""
    out: List[Violation] = []

    session = PlanSession("spec-schema-probe", main_job="probe", issue_ref="probe")
    try:
        session.add_unit(Unit(kind="wagon", ref="w",
                              spec=wagon_spec(theme="Ingest Pipeline")))
        out.append(_violation(
            _RULE, _LOC,
            "add_unit accepted a wagon whose theme is not kebab-case — a value that "
            "is present and wrong must be refused at Compose, or it reaches plan/ "
            "unread by any schema"))
    except SessionGateError:
        pass

    # An unfinished draft is not a defect: the upsert exists to let it be re-stated.
    drafting = PlanSession("spec-schema-draft", main_job="probe", issue_ref="probe")
    try:
        drafting.add_unit(Unit(kind="wagon", ref="w", spec={"wagon": "manage-probe"}))
    except SessionGateError as exc:
        out.append(_violation(
            _RULE, _LOC,
            f"add_unit refused an incomplete DRAFT ({exc}) — Compose is a drafting "
            f"loop, so completeness belongs at Ratify; refusing here makes the "
            f"stage unusable"))

    # A kind with no writer and no reasoning role must not ride through to author.
    try:
        drafting.add_unit(Unit(kind="wagonn", ref="typo", spec={}))
        out.append(_violation(
            _RULE, _LOC,
            "add_unit accepted an unknown kind — it would pass every Ratify gate "
            "and fail only at author, after the lock"))
    except SessionGateError:
        pass

    return out


def _scan_ratify(root: Path) -> List[Violation]:
    """Ratify adds completeness, fails closed, and never blocks on an advisory kind."""
    out: List[Violation] = []

    incomplete = PlanSession("spec-schema-ratify", step=Step.RATIFY.value,
                             issue_ref="probe")
    incomplete.units = [{"kind": "wagon", "ref": "w", "verdict": Verdict.KEEP.value,
                         "spec": {"wagon": "manage-probe"}}]
    try:
        incomplete.confirm(root)
        out.append(_violation(
            _RULE, _LOC_RATIFY,
            "confirm() locked a plan whose kept wagon spec would author a "
            "schema-invalid artifact"))
    except SessionGateError:
        if incomplete.locked:
            out.append(_violation(
                _RULE, _LOC_RATIFY,
                "confirm() raised but left the session LOCKED — the gate must fail "
                "closed, like the interlocking, verb-object and artifact-naming gates"))

    advisory = PlanSession("spec-schema-advisory", step=Step.RATIFY.value,
                           issue_ref="probe")
    advisory.units = [
        {"kind": "wagon", "ref": "w", "verdict": Verdict.KEEP.value,
         "spec": wagon_spec("manage-probe")},
        {"kind": "wmbt", "ref": "m", "verdict": Verdict.KEEP.value,
         "spec": {"wagon_slug": "manage-probe", "code": "E001",
                  "object_of_control": "time to manage a probe"}},
    ]
    try:
        advisory.confirm(root)
    except SessionGateError as exc:
        out.append(_violation(
            _RULE, _LOC_RATIFY,
            f"confirm() BLOCKED on an advisory kind ({exc}) — feature/wmbt schemas "
            f"reject most of this repo's own artifacts, so enforcing them would "
            f"refuse the decomposition atdd ships"))
    else:
        if not any(u.get("advisories") for u in advisory.units):
            out.append(_violation(
                _RULE, _LOC_RATIFY,
                "an advisory finding was neither raised nor recorded on the unit — "
                "it must ride on the session so it survives compaction"))

    return out


def _scan_ladder(root: Path) -> List[Violation]:
    """Ratify reports the dangling ladder, and reporting does not block."""
    out: List[Violation] = []
    session = PlanSession("granularity-probe", step=Step.RATIFY.value,
                          issue_ref="probe")
    session.units = [{"kind": "wagon", "ref": "w", "verdict": Verdict.KEEP.value,
                      "spec": wagon_spec("manage-probe")}]
    try:
        session.confirm(root)
    except SessionGateError as exc:
        out.append(_violation(
            _LADDER_RULE, _LOC_RATIFY,
            f"confirm() refused a wagons-only plan ({exc}) — the ladder report is "
            f"advisory by default; a plan may be composed incrementally"))
        return out

    report = session.granularity_report()
    missing = [r for r in ("feature", "wmbt", "acceptance") if r not in report["dangling"]]
    if missing:
        out.append(_violation(
            _LADDER_RULE, _LOC_RATIFY,
            f"a wagons-only plan locked without naming {missing} as dangling — the "
            f"operator is told nothing, which is the detection gap this rule closes"))
    return out


def _scan_corpus() -> List[Violation]:
    """Every ENFORCED kind must accept every artifact this repo ships."""
    out: List[Violation] = []
    plan = Path(find_repo_root(Path(__file__))) / "plan"
    if not plan.is_dir():
        return out
    for path in plan.glob("*/_*.yaml"):
        if path.parent.name.startswith("_"):
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:  # a malformed file is another validator's business
            continue
        if not isinstance(doc, dict) or "wagon" not in doc:
            continue
        _, findings = check_unit_spec("wagon", doc, stage="ratify")
        if findings:
            out.append(_violation(
                _RULE, f"{path}:1",
                f"an ENFORCED kind rejects an artifact already in plan/: "
                f"{findings[0]} — the tier is only defensible while it accepts the "
                f"corpus; demote the kind or repair the schema"))
    return out


def test_compose_refuses_a_malformed_enforced_spec():
    """planner.plan.spec-is-schema-valid — Compose, Ratify, and the enforce tier."""
    root = Path(find_repo_root(Path(__file__)))
    violations = _scan_compose() + _scan_ratify(root) + _scan_corpus()
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=violations)


def test_ratify_reports_the_dangling_ladder():
    """planner.plan.granularity-completeness — reports, never blocks."""
    root = Path(find_repo_root(Path(__file__)))
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID,
                                 violations=_scan_ladder(root))
