# URN: test:enforce-merge-authority:define-required-checks:D002-SMOKE-001-required-check-policy
# Acceptance: acc:enforce-merge-authority:D002-SMOKE-001-required-check-policy
# WMBT: wmbt:enforce-merge-authority:D002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end through the real `atdd state policy-check` CLI over a real checkout carrying the shipped policy and workflow, the pair is admitted zero; renaming a workflow job so a required context is emitted by nobody, or weakening branch protection to allow a bypass, is refused non-zero naming the drifted context and the weakened setting. Refs #1400.
"""required-check-policy holds end-to-end through the real CLI (D002-SMOKE-001).

wagon: enforce-merge-authority | feature: define-required-checks | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:D002

The policy is the difference between a workflow that runs and a workflow that *gates*. So
it is checked the way it will be checked in anger: the shipped policy and the shipped
workflow, copied into a real checkout, cross-checked by the real command.

Then the two ways it silently rots — a job renamed, so branch protection waits forever on a
context nobody emits; and a bypass allowed, so a gate exists and is stepped around. Both
leave a green-looking repository. Both are refused here. Refs #1400.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.state import policy

from ._live import atdd_state, install_policy, repo_on_bare_remote


@pytest.mark.smoke
def test_d002_smoke_001_required_check_policy(tmp_path) -> None:
    """The shipped pair passes; a renamed job and an allowed bypass are both refused."""
    _remote, repo = repo_on_bare_remote(tmp_path)
    install_policy(repo)

    # The shipped policy and the shipped workflow agree.
    result = atdd_state(repo, "policy-check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CI is the merge authority" in result.stdout

    # Rename a workflow job: the context the policy waits for is now emitted by nobody.
    workflow_path = repo / policy.WORKFLOW_RELATIVE
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    workflow["jobs"]["legal-transition"]["name"] = "transitions"
    workflow_path.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")

    drifted = atdd_state(repo, "policy-check")
    assert drifted.returncode == 1, drifted.stdout
    assert "context_drift" in drifted.stdout
    assert "legal-transition" in drifted.stdout        # required, and now emitted by nobody
    assert "transitions" in drifted.stdout             # emitted, and required by nobody
    assert "does not make required" in drifted.stdout

    # Restore the workflow, then weaken branch protection instead.
    install_policy(repo)
    policy_path = repo / policy.POLICY_RELATIVE
    document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    document["branch_protection"]["allow_bypass"] = True
    policy_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    bypass = atdd_state(repo, "policy-check")
    assert bypass.returncode == 1, bypass.stdout
    assert policy.CLAUSE_BYPASS in bypass.stdout
    assert "not a gate" in bypass.stdout

    # And a branch that need not be up to date with its base can pass every check against a
    # stale base and still break main on landing.
    install_policy(repo)
    document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    document["required_status_checks"]["strict"] = False
    policy_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    stale = atdd_state(repo, "policy-check")
    assert stale.returncode == 1, stale.stdout
    assert policy.CLAUSE_NOT_UP_TO_DATE in stale.stdout
