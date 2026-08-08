"""
Gate completion validation for COMPLETE issues.

Purpose: Verify that COMPLETE issues have deterministic evidence:
- Artifact paths verified against git (exist/changed/deleted)
- Release gate verified (version bumped, tag on HEAD)

Gate-test-command execution was removed in #1683. It parsed a markdown table out of
the issue body and ran each cell through ``sh``, so a cell written the ordinary way --
`cmd` (note) -- reached the shell with an unbalanced backquote. It also passed for free
when no table was present, which made documenting validation strictly costlier than
omitting it. The required ``validate-gate`` status check already covers the ground it
was approximating.

This is the CI counterpart to the CLI checks in ``atdd update --status COMPLETE``.

Run: atdd validate coach
"""

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.coach.utils.artifact_claims import (
    RULE_CLAIMS_RESOLVE,
    RULE_MUST_BE_DECLARED,
    VALIDATOR_ID,
)
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule

pytestmark = [pytest.mark.platform, pytest.mark.github_api]

REPO_ROOT = find_repo_root()

# SPEC-COACH-RULEID-0007: bound at module-import time, so a rule this validator
# enforces but no convention declares fails loudly at collection rather than
# silently enforcing a docstring. Before #1726 this file called bind_rule zero
# times while guarding the COMPLETE gate.
#
# The ids are spelled as LITERALS here, not as the imported constants, because
# reverse rule-coherence (test_rule_validator_binding) reads this file with `ast`
# and can only follow a literal or a module-level string constant — an imported
# name resolves to nothing, and the rules would read as orphaned. The asserts
# below are what stop the two spellings from drifting.
_RULE_RESOLVE = bind_rule("coach.issue.artifact-claims-must-resolve")
_RULE_DECLARED = bind_rule("coach.issue.artifacts-must-be-declared")

assert _RULE_RESOLVE.rule_id == RULE_CLAIMS_RESOLVE
assert _RULE_DECLARED.rule_id == RULE_MUST_BE_DECLARED


# ---------------------------------------------------------------------------
# SPEC-GATE-0002: Artifact claims must be valid for COMPLETE issues
# ---------------------------------------------------------------------------

def test_complete_issues_artifacts_valid(github_complete_issues):
    """
    SPEC-GATE-0002 / ``coach.issue.artifact-claims-must-resolve`` +
    ``coach.issue.artifacts-must-be-declared``.

    Given: Issues labelled atdd:COMPLETE
    When: Parsing the Artifacts section and checking it with the shared checker
    Then: Created files exist, Modified files changed, Deleted files are gone —
          AND the section is a complete record of what the work changed.

    The policy lives in ``atdd.coach.utils.artifact_claims``, which the runtime
    gate in ``IssueManager`` also calls. This validator used to carry its own
    copy, including its own ``total == 0`` escape that skipped any issue
    declaring nothing — so the issues with the least evidence were the ones
    checked least (#1726). Pass/fail is now the rules' declared disposition,
    not a hard-coded verdict here.
    """
    manager = IssueManager(target_dir=REPO_ROOT)

    violations = []
    for issue in github_complete_issues:
        # #1611: a COMPLETE issue's PR has merged by definition, so the claims are
        # read against the commit that landed them — `main...HEAD` is empty here.
        report = manager.check_artifacts(
            manager._parse_artifacts(issue.get("body", "") or ""),
            force=False,
            issue_number=issue["number"],
        )
        violations.extend(report.violations)

    assert_disposition_satisfied(validator_id=VALIDATOR_ID, violations=violations)


# ---------------------------------------------------------------------------
# SPEC-GATE-0003: Release gate must be satisfied for COMPLETE issues
# ---------------------------------------------------------------------------

def test_complete_issues_release_gate(github_complete_issues):
    """
    SPEC-GATE-0003: COMPLETE issues require a resolved release version (#1172).

    Given: Issues labelled atdd:COMPLETE
    When: Checking the release gate
    Then: The State Store's singleton ``release`` object resolves a real version
          (``atdd state version show``) — NOT the local ``0.0.0+local`` fallback.

    Post-#1172 the release version lives in the State Store, not a static
    ``pyproject.toml`` line or a git tag (tag + publish are operator-coordinated
    post-merge per ``CLAUDE.md::release``). This validates the overall release
    state, not per-issue: if any COMPLETE issue exists, a version must be set.
    """
    import os
    base_ref = os.environ.get("GITHUB_BASE_REF", "")
    github_ref = os.environ.get("GITHUB_REF", "")
    if base_ref or (github_ref and github_ref != "refs/heads/main"):
        pytest.skip("Release gate skipped on PR branches (version bumped post-merge)")

    manager = IssueManager(target_dir=REPO_ROOT)

    # Release gate is a repo-level check, not per-issue: the store must hold a
    # real release version.
    valid, messages = manager._verify_release_gate(force=False)

    assert valid, (
        f"\nRelease gate not satisfied for COMPLETE issues.\n"
        f"Fix: bump the version — atdd state version bump --class PATCH|MINOR|MAJOR.\n\n"
        + "\n".join(messages)
    )
