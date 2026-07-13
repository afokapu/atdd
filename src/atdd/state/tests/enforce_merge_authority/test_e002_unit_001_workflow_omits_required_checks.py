# URN: test:enforce-merge-authority:run-merge-checks:E002-UNIT-001-workflow-omits-required-checks
# Acceptance: acc:enforce-merge-authority:E002-UNIT-001-workflow-omits-required-checks
# WMBT: wmbt:enforce-merge-authority:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the merge-authority workflow triggers on BOTH push and pull_request, and every one of the seven section-4 required checks (canonicality, schema, legal transition, trailer cross-check, field-writer, no-secrets, core no-provider) is present as a job that emits it as a status-check context. Refs #1400.
"""The merge-authority workflow runs the whole required-check set (E002-UNIT-001).

wagon: enforce-merge-authority | feature: run-merge-checks | phase: RED
WMBT: wmbt:enforce-merge-authority:E002

Invariant I6: local hooks are convenience; CI is authority. That is only true if every
gate a hook can run has an equivalent server-side job — and if those jobs run on **push**
as well as on **pull request**, because a branch that is never PR'd still reaches the
protected branch through a merge somewhere.

The check set is section 4's, in full. A workflow missing one of the seven is not "mostly"
the merge authority; it is a merge authority with a documented hole in it. Refs #1400.
"""
from __future__ import annotations

from atdd.state import policy
from atdd.state.merge_authority import (
    CHECK_CANONICALITY,
    CHECK_FIELD_WRITER,
    CHECK_NO_PROVIDER,
    CHECK_NO_SECRETS,
    CHECK_SCHEMA,
    CHECK_TRAILER,
    CHECK_TRANSITION,
    REQUIRED_CHECKS,
)

from ._helpers import repo_root


def test_e002_unit_001_workflow_omits_required_checks() -> None:
    """The workflow triggers on push and pull_request, and every section-4 check is a job."""
    root = repo_root()
    assert (root / policy.WORKFLOW_RELATIVE).is_file(), "the merge-authority workflow must exist"
    workflow = policy.load_workflow(root)

    # The workflow triggers on BOTH push and pull_request (spec §9: push CI and PR CI).
    triggers = policy.workflow_triggers(workflow)
    assert "push" in triggers
    assert "pull_request" in triggers

    # Every section-4 required check is present as a job, emitting its own context.
    contexts = policy.workflow_contexts(workflow)
    assert set(REQUIRED_CHECKS) == {
        CHECK_CANONICALITY, CHECK_SCHEMA, CHECK_TRANSITION, CHECK_TRAILER,
        CHECK_FIELD_WRITER, CHECK_NO_SECRETS, CHECK_NO_PROVIDER,
    }
    for check in REQUIRED_CHECKS:
        assert check in contexts, f"the workflow emits no context for the required check {check}"

    # No job is advisory: continue-on-error would report the failure and merge anyway.
    assert policy.advisory_jobs(workflow) == []

    # Every job actually runs the check it is named for — a job named `legal-transition`
    # that runs something else emits a green context that means nothing.
    for key, job in workflow["jobs"].items():
        commands = " ".join(str(step.get("run", "")) for step in job["steps"])
        assert "atdd state merge-authority" in commands
        assert f"--check {key}" in commands
