# URN: test:enforce-merge-authority:define-required-checks:D002-UNIT-001-policy-check-contexts-drift
# Acceptance: acc:enforce-merge-authority:D002-UNIT-001-policy-check-contexts-drift
# WMBT: wmbt:enforce-merge-authority:D002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the shipped policy's required status-check contexts and the contexts the merge-authority workflow actually emits are compared in BOTH directions — every required context is emitted, every section-4 check the workflow emits is listed as required — and a drift in either direction is reported naming the context. Refs #1400.
"""The policy and the workflow may not drift apart (D002-UNIT-001).

wagon: enforce-merge-authority | feature: define-required-checks | phase: RED
WMBT: wmbt:enforce-merge-authority:D002

A CI workflow that is not wired into branch protection is *advisory*: it can go red and
the merge lands anyway. The policy is what turns the run into a gate — and the failure it
must catch is drift, which is silent by construction. Rename a job and the required
context it used to emit is never reported again; branch protection waits forever for a
check that no longer exists, or (worse, and this is the real one) stops waiting and lets
everything through.

So the two are compared as equal sets, in both directions, over the *shipped* files. Refs #1400.
"""
from __future__ import annotations

from atdd.state import policy
from atdd.state.merge_authority import REQUIRED_CHECKS

from ._helpers import repo_root


def test_d002_unit_001_policy_check_contexts_drift() -> None:
    """The shipped policy and workflow agree; a drift in either direction is reported."""
    root = repo_root()
    report = policy.check_policy(root)

    # The shipped pair agrees today — which is the state the gate exists to preserve.
    assert report.ok, report.render()

    # Every required context in the policy is emitted by the workflow.
    for context in report.policy_contexts:
        assert context in report.workflow_contexts

    # Every section-4 check the workflow emits is listed as required in the policy.
    for check in REQUIRED_CHECKS:
        assert check in report.policy_contexts
        assert check in report.workflow_contexts

    workflow = policy.load_workflow(root)
    shipped = policy.load_policy(root)

    # Drift in one direction: the workflow renames a job. The context the policy waits for
    # is now emitted by nobody.
    renamed = {**workflow, "jobs": {
        key: ({**job, "name": "renamed-job"} if key == "legal-transition" else job)
        for key, job in workflow["jobs"].items()
    }}
    drifted = _cross_check(shipped, renamed)
    assert not drifted.ok
    assert any("legal-transition" in problem for problem in drifted.problems)
    assert any(policy.CLAUSE_DRIFT in problem for problem in drifted.problems)

    # Drift in the other direction: a check is added to the workflow and never made
    # required. It runs, it goes red, and the merge lands anyway.
    added = {**workflow, "jobs": {**workflow["jobs"], "new-check": {"name": "new-check"}}}
    drifted = _cross_check(shipped, added)
    assert not drifted.ok
    assert any("new-check" in problem and "does not make required" in problem
               for problem in drifted.problems)

    # And a section-4 check dropped from the policy is named as such.
    thinned = {
        **shipped,
        "required_status_checks": {
            **shipped["required_status_checks"],
            "contexts": [c for c in shipped["required_status_checks"]["contexts"]
                         if c != "no-secrets"],
        },
    }
    drifted = _cross_check(thinned, workflow)
    assert not drifted.ok
    assert any(policy.CLAUSE_MISSING_SECTION_4 in problem and "no-secrets" in problem
               for problem in drifted.problems)


def _cross_check(shipped_policy, shipped_workflow, tmp=None):
    """Run the real cross-check against an in-memory (drifted) policy/workflow pair."""
    import tempfile

    import yaml

    from pathlib import Path

    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / policy.POLICY_RELATIVE).parent.mkdir(parents=True, exist_ok=True)
        (root / policy.WORKFLOW_RELATIVE).parent.mkdir(parents=True, exist_ok=True)
        (root / policy.POLICY_RELATIVE).write_text(
            yaml.safe_dump(shipped_policy, sort_keys=False), encoding="utf-8")
        (root / policy.WORKFLOW_RELATIVE).write_text(
            yaml.safe_dump(shipped_workflow, sort_keys=False), encoding="utf-8")
        return policy.check_policy(root)
