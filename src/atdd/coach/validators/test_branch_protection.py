"""
C003: Branch protection drift detection.

Validates that the GitHub branch-protection rules on ``main`` match the
ATDD-expected contract.  Detects:

1. Missing protection (no rule set on main)
2. Drifted protection (rule exists but differs from expected policy)
3. Degraded mode (insufficient permissions to verify)

SPEC: SPEC-COACH-C003
Acceptance URNs:
  acc:branch-protection-drift-detection:C003-PLATFORM-001-protection-enforced
  acc:branch-protection-drift-detection:C003-PLATFORM-002-status-checks-present
  acc:branch-protection-drift-detection:C003-PLATFORM-003-enforce-admins-enabled
  acc:branch-protection-drift-detection:C003-PLATFORM-004-pr-reviews-required

These tests run against the LIVE GitHub API and require:
- .atdd/config.yaml with github.repo
- gh CLI authenticated with admin or repo scope

Run: atdd validate coach
"""
import pytest

from atdd.coach.commands.branch_protection import (
    EXPECTED_POLICY,
    ProtectionStatus,
    verify_branch_protection,
)

pytestmark = [pytest.mark.platform, pytest.mark.github_api]


# Fixtures: repo_name and protection_result are in conftest.py (session-scoped, prefetched)

# ---------------------------------------------------------------------------
# C003 validators
# ---------------------------------------------------------------------------


def test_branch_protection_enforced(protection_result):
    """
    SPEC-COACH-C003-0001: Branch protection on main matches ATDD contract.

    Given: An ATDD-managed repository with github.repo in config
    When: Querying branch protection rules via GitHub REST API
    Then: The protection status is ENFORCED (no drift)
    """
    status, details = protection_result

    assert status == ProtectionStatus.ENFORCED, (
        f"\nBranch protection on main is {status.value}.\n"
        + (
            "Drift details:\n  " + "\n  ".join(details)
            if details
            else "No protection rule found on main."
        )
        + "\n\nFix: Run `atdd init --force` to re-apply branch protection, "
        "or manually configure via GitHub repo settings."
    )


def test_expected_policy_requires_status_checks(protection_result):
    """
    SPEC-COACH-C003-0002: Expected policy includes validate-gate status check.

    Given: The ATDD branch protection contract
    When: Inspecting required_status_checks
    Then: validate-gate is a required context and strict mode is enabled
    """
    expected_checks = EXPECTED_POLICY["required_status_checks"]
    assert "validate-gate" in expected_checks["contexts"], (
        "ATDD contract is missing validate-gate in required_status_checks.contexts"
    )
    assert expected_checks["strict"] is True, (
        "ATDD contract should require branches to be up to date (strict=True)"
    )


def test_expected_policy_enforces_admins(protection_result):
    """
    SPEC-COACH-C003-0003: Expected policy enforces rules for admins.

    Given: The ATDD branch protection contract
    When: Inspecting enforce_admins
    Then: Admin enforcement is enabled (no bypass)
    """
    assert EXPECTED_POLICY["enforce_admins"] is True, (
        "ATDD contract should enforce branch protection for admins"
    )


def test_expected_policy_requires_pr_reviews(protection_result):
    """
    SPEC-COACH-C003-0004: Expected policy requires pull request reviews.

    Given: The ATDD branch protection contract
    When: Inspecting required_pull_request_reviews
    Then: PR reviews are required (review count >= 0)
    """
    pr_config = EXPECTED_POLICY.get("required_pull_request_reviews")
    assert pr_config is not None, (
        "ATDD contract should include required_pull_request_reviews"
    )
    assert "required_approving_review_count" in pr_config, (
        "ATDD contract should specify required_approving_review_count"
    )
