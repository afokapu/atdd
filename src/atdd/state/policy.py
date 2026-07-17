"""The required-check policy — what makes CI the authority (#1400 enforce-merge-authority).

A workflow that runs but is not *required* is a suggestion. Every check in the
merge-authority run can be green, red, or never run at all, and a merge still lands —
unless branch protection names those checks as required status contexts and forbids the
bypass. So the policy document is not documentation: it is the machine-readable statement
of which contexts must be green, and of the two protection settings that turn them into a
gate (I6).

The failure this prevents is **drift**: a job renamed in the workflow, or a check added to
the required set and never wired into protection, leaves a hole nobody sees — the run
still looks green, and the gate it was supposed to be silently isn't one. So the policy
and the workflow are cross-checked as *equal sets* (D002), in both directions:

- every context the policy requires is emitted by the workflow, and
- every job the workflow emits is required by the policy.

The policy lives at :data:`POLICY_RELATIVE` and the workflow at :data:`WORKFLOW_RELATIVE`.
A GitHub status-check context is the job's ``name`` (falling back to its key), so those
names — and not the job ids — are what the policy pins.

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set

import yaml

from atdd.state.merge_authority import REQUIRED_CHECKS

_log = logging.getLogger(__name__)

#: The branch-protection / required-checks policy, repo-relative.
POLICY_RELATIVE = Path(".github") / "atdd-merge-authority-policy.yaml"

#: The workflow that emits the required contexts, repo-relative.
WORKFLOW_RELATIVE = Path(".github") / "workflows" / "atdd-merge-authority.yml"

#: The events the merge-authority run must trigger on (spec §9: push CI *and* PR CI).
REQUIRED_TRIGGERS = ("push", "pull_request")

#: Clause names a policy refusal carries.
CLAUSE_DRIFT = "context_drift"
CLAUSE_MISSING_SECTION_4 = "missing_required_check"
CLAUSE_BYPASS = "bypass_allowed"
CLAUSE_NOT_UP_TO_DATE = "stale_branch_admitted"
CLAUSE_AUTHORITY = "authority_not_stated"
CLAUSE_ADVISORY_JOB = "advisory_job"
CLAUSE_TRIGGER = "missing_trigger"


class PolicyError(RuntimeError):
    """The policy or the workflow could not be read (D002)."""


@dataclass(frozen=True)
class PolicyReport:
    """The outcome of cross-checking the policy against the workflow it governs."""

    policy_contexts: List[str] = field(default_factory=list)
    workflow_contexts: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def render(self) -> str:
        if self.ok:
            return (
                "the required-check policy and the merge-authority workflow agree "
                f"({len(self.policy_contexts)} required context(s)); CI is the merge authority"
            )
        lines = [f"required-check policy problem(s) ({len(self.problems)}):"]
        lines.extend(f"  - {problem}" for problem in self.problems)
        return "\n".join(lines)


def load_policy(root: Path) -> Dict[str, Any]:
    """Read the branch-protection policy document."""
    path = Path(root) / POLICY_RELATIVE
    if not path.is_file():
        raise PolicyError(f"no required-check policy at {POLICY_RELATIVE}")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise PolicyError(f"{POLICY_RELATIVE}: not a YAML mapping")
    return document


def load_workflow(root: Path) -> Dict[str, Any]:
    """Read the merge-authority workflow definition."""
    path = Path(root) / WORKFLOW_RELATIVE
    if not path.is_file():
        raise PolicyError(f"no merge-authority workflow at {WORKFLOW_RELATIVE}")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise PolicyError(f"{WORKFLOW_RELATIVE}: not a YAML mapping")
    return document


def workflow_contexts(workflow: Mapping[str, Any]) -> List[str]:
    """The status-check contexts a workflow emits — one per job, by its ``name``."""
    jobs = workflow.get("jobs") or {}
    return sorted(
        str((job or {}).get("name") or key)
        for key, job in jobs.items()
    )


def workflow_triggers(workflow: Mapping[str, Any]) -> Set[str]:
    """The events the workflow runs on. ``on:`` parses as the boolean ``True`` in YAML 1.1."""
    trigger = workflow.get("on", workflow.get(True))
    if isinstance(trigger, str):
        return {trigger}
    if isinstance(trigger, list):
        return {str(item) for item in trigger}
    if isinstance(trigger, Mapping):
        return {str(key) for key in trigger}
    return set()


def advisory_jobs(workflow: Mapping[str, Any]) -> List[str]:
    """Every job the workflow lets fail without failing the run — there must be none (I6)."""
    jobs = workflow.get("jobs") or {}
    return sorted(
        str((job or {}).get("name") or key)
        for key, job in jobs.items()
        if (job or {}).get("continue-on-error")
    )


def policy_contexts(policy: Mapping[str, Any]) -> List[str]:
    """The status-check contexts branch protection makes required."""
    checks = policy.get("required_status_checks") or {}
    return sorted(str(context) for context in (checks.get("contexts") or []))


def check_policy(root: Path) -> PolicyReport:
    """Cross-check the policy against the workflow, and pin the protection settings (D002)."""
    policy = load_policy(root)
    workflow = load_workflow(root)

    required = policy_contexts(policy)
    emitted = workflow_contexts(workflow)
    problems: List[str] = []

    for context in required:
        if context not in emitted:
            problems.append(
                f"[{CLAUSE_DRIFT}] the policy requires the context {context!r}, which the "
                f"workflow does not emit"
            )
    for context in emitted:
        if context not in required:
            problems.append(
                f"[{CLAUSE_DRIFT}] the workflow emits the context {context!r}, which the policy "
                f"does not make required — it would run, go red, and merge anyway"
            )
    for check in REQUIRED_CHECKS:
        if check not in required:
            problems.append(
                f"[{CLAUSE_MISSING_SECTION_4}] the section-4 required check {check!r} is not "
                f"listed as required in the policy"
            )

    triggers = workflow_triggers(workflow)
    for event in REQUIRED_TRIGGERS:
        if event not in triggers:
            problems.append(
                f"[{CLAUSE_TRIGGER}] the workflow does not trigger on {event!r}"
            )

    for job in advisory_jobs(workflow):
        problems.append(
            f"[{CLAUSE_ADVISORY_JOB}] the job {job!r} is continue-on-error, so it reports a "
            "failure and merges anyway"
        )

    protection = policy.get("branch_protection") or {}
    if protection.get("allow_bypass") is not False:
        problems.append(
            f"[{CLAUSE_BYPASS}] the policy must set branch_protection.allow_bypass: false — a "
            "gate anyone can step around is not a gate"
        )
    if protection.get("enforce_admins") is not True:
        problems.append(
            f"[{CLAUSE_BYPASS}] the policy must set branch_protection.enforce_admins: true"
        )
    if (policy.get("required_status_checks") or {}).get("strict") is not True:
        problems.append(
            f"[{CLAUSE_NOT_UP_TO_DATE}] the policy must set required_status_checks.strict: true "
            "so a branch is up to date with the base before it merges"
        )

    authority = policy.get("authority") or {}
    if not (authority.get("hooks_are_convenience") is True
            and authority.get("ci_is_authority") is True):
        problems.append(
            f"[{CLAUSE_AUTHORITY}] the policy must state that local hooks are convenience and "
            "CI/branch protection is authority (I6)"
        )

    report = PolicyReport(policy_contexts=required, workflow_contexts=emitted, problems=problems)
    if not report.ok:
        _log.warning("required-check policy drift", extra={"problems": len(problems)})
    return report


def protected_branch(root: Path) -> Optional[str]:
    """The branch the policy protects."""
    return load_policy(root).get("protected_branch")
