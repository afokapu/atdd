"""The cross-repo rollout and rollback plan (#1400 X-006, P001).

The migration has one-way doors in it. Deleting the manifest readers, flipping the canonicality
gate to required — those are steps that a bad afternoon cannot simply undo, and they are steps
taken across **two repos** that ship on their own schedules. A plan for that is not paperwork; it
is the difference between "we rolled back" and "we are now debugging a half-migrated monorepo at
nine at night."

So the plan is **data**, not prose, and it is checked (P001):

``shadow-before-blocking``
    Shadow mode is scheduled strictly before every blocking step and before every removal. You do
    not get to delete the fallback and *then* find out whether the thing replacing it agrees with
    it. This is the single most important ordering constraint in the wagon, and it is the one a
    schedule under pressure will quietly violate.

``irreversible-has-rollback``
    Every irreversible step names a **rollback trigger** ("what will tell us this went wrong")
    and a **restore procedure** ("what exactly do we type"). A step whose rollback is "revert the
    commit" has not been thought about: reverting the commit that deleted the readers does not
    restore the manifest that has since gone stale.

``irreversible-after-dependency``
    No irreversible step is scheduled before a step it depends on. Cheap to state, and the whole
    reason the dependency graph is written down.

``agreed-before-irreversible``
    Every repo the plan touches has signed off *before* the first irreversible step. A one-way
    door opened by one repo, on behalf of two, is not a migration — it is an outage with a commit
    message.

Dependency discipline: stdlib + ``pyyaml``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

_log = logging.getLogger(__name__)

#: The authored plan, relative to the repo root.
PLAN_RELATIVE = Path(".atdd") / "policy" / "migration-rollout.yaml"

#: A step runs in one of two modes. The distinction is the point of the whole plan.
MODE_SHADOW = "shadow"
MODE_BLOCKING = "blocking"
MODES = (MODE_SHADOW, MODE_BLOCKING)

RULE_SHADOW_BEFORE_BLOCKING = "shadow-before-blocking"
RULE_IRREVERSIBLE_HAS_ROLLBACK = "irreversible-has-rollback"
RULE_IRREVERSIBLE_AFTER_DEPENDENCY = "irreversible-after-dependency"
RULE_AGREED_BEFORE_IRREVERSIBLE = "agreed-before-irreversible"
RULE_MALFORMED = "malformed-plan"


class RolloutError(RuntimeError):
    """The plan is missing or unreadable. Not a finding — a failure to even evaluate."""


@dataclass(frozen=True)
class Rollback:
    """How a step is undone: what tells you to, and what exactly you do."""

    trigger: str
    restore: str

    @property
    def complete(self) -> bool:
        return bool(self.trigger.strip()) and bool(self.restore.strip())


@dataclass(frozen=True)
class Step:
    """One step of the cross-repo cutover."""

    id: str
    order: int
    mode: str
    repos: List[str]
    reversible: bool
    summary: str = ""
    depends_on: List[str] = field(default_factory=list)
    rollback: Optional[Rollback] = None

    @property
    def irreversible(self) -> bool:
        return not self.reversible


@dataclass(frozen=True)
class Plan:
    """The authored plan: its steps, and who has agreed to it."""

    steps: List[Step] = field(default_factory=list)
    #: repo → the sign-off recorded for it. The plan is agreed when every touched repo appears.
    agreed_by: Dict[str, str] = field(default_factory=dict)

    def by_id(self, step_id: str) -> Optional[Step]:
        return next((step for step in self.steps if step.id == step_id), None)

    @property
    def ordered(self) -> List[Step]:
        return sorted(self.steps, key=lambda step: step.order)

    @property
    def repos(self) -> List[str]:
        return sorted({repo for step in self.steps for repo in step.repos})

    @property
    def first_irreversible(self) -> Optional[Step]:
        return next((step for step in self.ordered if step.irreversible), None)


@dataclass(frozen=True)
class RolloutProblem:
    """One thing wrong with the plan."""

    rule: str
    step: str
    detail: str

    def render(self) -> str:
        return f"[{self.rule}] {self.step}: {self.detail}"


@dataclass(frozen=True)
class RolloutReport:
    """The verdict over the authored plan."""

    problems: List[RolloutProblem] = field(default_factory=list)
    plan: Optional[Plan] = None

    @property
    def ok(self) -> bool:
        return not self.problems

    def render(self) -> str:
        if self.ok:
            plan = self.plan
            steps = len(plan.steps) if plan else 0
            irreversible = len([s for s in plan.steps if s.irreversible]) if plan else 0
            return (
                f"the rollout plan is sound: {steps} step(s), shadow mode before every blocking "
                f"step and every removal, {irreversible} irreversible step(s) each carrying a "
                f"rollback trigger and a restore procedure, agreed across "
                f"{', '.join(plan.repos) if plan else ''} before the first one-way door."
            )
        return "\n".join([
            f"the rollout plan has {len(self.problems)} problem(s):",
            *(f"  {problem.render()}" for problem in self.problems),
        ])


def _step_from(raw: Dict[str, Any], index: int) -> Step:
    rollback_raw = raw.get("rollback") or {}
    rollback = (
        Rollback(trigger=str(rollback_raw.get("trigger") or ""),
                 restore=str(rollback_raw.get("restore") or ""))
        if rollback_raw else None
    )
    return Step(
        id=str(raw.get("id") or f"<step {index}>"),
        order=int(raw.get("order", index)),
        mode=str(raw.get("mode") or ""),
        repos=[str(repo) for repo in (raw.get("repos") or [])],
        reversible=bool(raw.get("reversible", False)),
        summary=str(raw.get("summary") or ""),
        depends_on=[str(dep) for dep in (raw.get("depends_on") or [])],
        rollback=rollback,
    )


def load_plan(path: Path) -> Plan:
    """Read and shape the authored plan, or raise :class:`RolloutError` naming the file."""
    path = Path(path)
    if not path.is_file():
        raise RolloutError(f"no rollout plan at {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RolloutError(f"{path} is not readable YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise RolloutError(f"{path}: not a YAML mapping")

    raw_steps = document.get("steps") or []
    if not isinstance(raw_steps, list):
        raise RolloutError(f"{path}: `steps` is not a list")

    return Plan(
        steps=[_step_from(raw, index) for index, raw in enumerate(raw_steps) if isinstance(raw, dict)],
        agreed_by={str(k): str(v) for k, v in (document.get("agreed_by") or {}).items()},
    )


def _check_shadow_before_blocking(plan: Plan) -> List[RolloutProblem]:
    """Shadow mode precedes every blocking step and every irreversible removal (P001-UNIT-001)."""
    shadow = [step for step in plan.ordered if step.mode == MODE_SHADOW]
    if not shadow:
        return [RolloutProblem(
            RULE_SHADOW_BEFORE_BLOCKING, "<plan>",
            "the plan schedules no shadow-mode step at all — blocking mode would be turned on "
            "with no evidence that the projection and the thing it replaces agree",
        )]
    first_shadow = shadow[0].order
    problems: List[RolloutProblem] = []
    for step in plan.ordered:
        gated = step.mode == MODE_BLOCKING or step.irreversible
        if gated and step.order <= first_shadow:
            problems.append(RolloutProblem(
                RULE_SHADOW_BEFORE_BLOCKING, step.id,
                f"is {'blocking' if step.mode == MODE_BLOCKING else 'irreversible'} at order "
                f"{step.order}, but the first shadow step ({shadow[0].id}) is at order "
                f"{first_shadow} — shadow mode must come strictly first",
            ))
    return problems


def _check_rollbacks(plan: Plan) -> List[RolloutProblem]:
    """Every irreversible step names a trigger and a restore procedure (P001-UNIT-002)."""
    problems: List[RolloutProblem] = []
    for step in plan.ordered:
        if step.reversible:
            continue
        if step.rollback is None:
            problems.append(RolloutProblem(
                RULE_IRREVERSIBLE_HAS_ROLLBACK, step.id,
                "is irreversible and names no rollback at all",
            ))
        elif not step.rollback.complete:
            missing = [
                name for name, value in
                (("trigger", step.rollback.trigger), ("restore", step.rollback.restore))
                if not value.strip()
            ]
            problems.append(RolloutProblem(
                RULE_IRREVERSIBLE_HAS_ROLLBACK, step.id,
                f"is irreversible and its rollback names no {' and no '.join(missing)}",
            ))
    return problems


def _check_dependencies(plan: Plan) -> List[RolloutProblem]:
    """No irreversible step runs before something it depends on (P001-UNIT-002)."""
    problems: List[RolloutProblem] = []
    for step in plan.ordered:
        for dep_id in step.depends_on:
            dep = plan.by_id(dep_id)
            if dep is None:
                problems.append(RolloutProblem(
                    RULE_MALFORMED, step.id,
                    f"depends on {dep_id!r}, which the plan does not define",
                ))
            elif dep.order >= step.order:
                problems.append(RolloutProblem(
                    RULE_IRREVERSIBLE_AFTER_DEPENDENCY, step.id,
                    f"is at order {step.order} but depends on {dep.id} at order {dep.order} — "
                    "a step may not run before what it depends on",
                ))
    return problems


def _check_agreement(plan: Plan) -> List[RolloutProblem]:
    """Every repo the plan touches has agreed, before the first one-way door."""
    first = plan.first_irreversible
    if first is None:
        return []
    missing = [repo for repo in plan.repos if repo not in plan.agreed_by]
    if not missing:
        return []
    return [RolloutProblem(
        RULE_AGREED_BEFORE_IRREVERSIBLE, first.id,
        f"is the first irreversible step, but {', '.join(missing)} "
        f"{'has' if len(missing) == 1 else 'have'} not agreed to the plan "
        f"(agreed: {sorted(plan.agreed_by) or 'nobody'})",
    )]


def check(root: Path, *, plan_path: Optional[Path] = None) -> RolloutReport:
    """Check the authored rollout plan (P001). Raises :class:`RolloutError` if there is none."""
    path = Path(plan_path) if plan_path is not None else Path(root) / PLAN_RELATIVE
    plan = load_plan(path)

    problems: List[RolloutProblem] = []
    for rule in (_check_shadow_before_blocking, _check_rollbacks,
                 _check_dependencies, _check_agreement):
        problems.extend(rule(plan))

    if problems:
        _log.warning(
            "the migration rollout plan is not sound",
            extra={"plan": str(path), "problems": [p.render() for p in problems]},
        )
    return RolloutReport(problems=problems, plan=plan)


def steps_of(root: Path, *, plan_path: Optional[Path] = None) -> Sequence[Step]:
    """The plan's steps in scheduled order (used by the runbook cross-check and the tests)."""
    path = Path(plan_path) if plan_path is not None else Path(root) / PLAN_RELATIVE
    return load_plan(path).ordered


__all__ = [
    "MODES", "MODE_BLOCKING", "MODE_SHADOW", "PLAN_RELATIVE", "Plan", "RULE_AGREED_BEFORE_IRREVERSIBLE",
    "RULE_IRREVERSIBLE_AFTER_DEPENDENCY", "RULE_IRREVERSIBLE_HAS_ROLLBACK", "RULE_MALFORMED",
    "RULE_SHADOW_BEFORE_BLOCKING", "Rollback", "RolloutError", "RolloutProblem", "RolloutReport",
    "Step", "check", "load_plan", "steps_of",
]
