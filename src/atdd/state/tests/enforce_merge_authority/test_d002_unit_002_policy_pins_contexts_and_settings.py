# URN: test:enforce-merge-authority:define-required-checks:D002-UNIT-002-policy-pins-contexts-and-settings
# Acceptance: acc:enforce-merge-authority:D002-UNIT-002-policy-pins-contexts-and-settings
# WMBT: wmbt:enforce-merge-authority:D002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the policy's required contexts and the workflow's emitted contexts are equal sets; the policy pins branch protection to disallow bypass on the protected branch, requires branches to be up to date with the base before merge, and states that local hooks are convenience while CI is authority (I6) — and dropping any one of those settings is refused. Refs #1400.
"""The policy pins the contexts AND the settings that make them a gate (D002-UNIT-002).

wagon: enforce-merge-authority | feature: define-required-checks | phase: RED
WMBT: wmbt:enforce-merge-authority:D002

Naming the required contexts is only half of it. Two protection settings decide whether
those contexts are a gate or a formality:

- **no bypass.** A check an administrator can step around is not a check, and "just this
  once" is exactly how the projection acquires a state no validator ever admitted.
- **up to date with the base.** Without it a branch passes every check against a stale
  base and breaks main on landing — every check green, and the merge still wrong.

And the policy has to *say* the thing the whole model rests on: local hooks are
convenience, CI is authority (I6). A hook can be skipped with ``--no-verify``; nobody but
the developer who ran it can rely on its result. Refs #1400.
"""
from __future__ import annotations

import copy

from atdd.state import policy
from atdd.state.merge_authority import REQUIRED_CHECKS

from ._helpers import repo_root
from .test_d002_unit_001_policy_check_contexts_drift import _cross_check


def test_d002_unit_002_policy_pins_contexts_and_settings() -> None:
    """Equal sets, no bypass, no stale branch, and CI named as the authority."""
    root = repo_root()
    shipped = policy.load_policy(root)
    workflow = policy.load_workflow(root)
    report = policy.check_policy(root)
    assert report.ok, report.render()

    # The policy's required contexts and the workflow's emitted contexts are EQUAL SETS.
    assert set(report.policy_contexts) == set(report.workflow_contexts)
    assert set(report.policy_contexts) == set(REQUIRED_CHECKS)

    # The policy protects a branch, and pins branch protection to disallow bypass on it.
    assert policy.protected_branch(root) == "main"
    assert shipped["branch_protection"]["allow_bypass"] is False
    assert shipped["branch_protection"]["enforce_admins"] is True

    # The policy requires branches to be up to date with the base before merge.
    assert shipped["required_status_checks"]["strict"] is True

    # The policy states that local hooks are convenience and CI is authority (I6).
    assert shipped["authority"]["invariant"] == "I6"
    assert shipped["authority"]["hooks_are_convenience"] is True
    assert shipped["authority"]["ci_is_authority"] is True
    assert "authority" in shipped["authority"]["statement"].lower()

    # Drop ANY one of those settings and the policy is refused — they are not decoration.
    for path, value, clause in (
        (("branch_protection", "allow_bypass"), True, policy.CLAUSE_BYPASS),
        (("branch_protection", "enforce_admins"), False, policy.CLAUSE_BYPASS),
        (("required_status_checks", "strict"), False, policy.CLAUSE_NOT_UP_TO_DATE),
        (("authority", "ci_is_authority"), False, policy.CLAUSE_AUTHORITY),
        (("authority", "hooks_are_convenience"), False, policy.CLAUSE_AUTHORITY),
    ):
        weakened = copy.deepcopy(shipped)
        weakened[path[0]][path[1]] = value
        drifted = _cross_check(weakened, workflow)
        assert not drifted.ok, f"{path} = {value} must be refused"
        assert any(clause in problem for problem in drifted.problems)

    # And no job in the workflow is continue-on-error: a job that reports a failure and
    # merges anyway is the advisory signal I6 forbids.
    assert policy.advisory_jobs(workflow) == []
    advisory = copy.deepcopy(workflow)
    advisory["jobs"]["no-secrets"]["continue-on-error"] = True
    drifted = _cross_check(shipped, advisory)
    assert not drifted.ok
    assert any(policy.CLAUSE_ADVISORY_JOB in problem for problem in drifted.problems)
