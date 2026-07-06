"""
Branch protection contract for ATDD-managed repositories.

Centralizes the expected branch-protection policy on ``main`` and provides
verification against the live GitHub API state.  Used by ``init``, ``sync``,
and the ``test_branch_protection`` validator to enforce a single source of
truth.

Policy summary (applied via GitHub REST API):
  - Require status check ``validate-gate`` to pass before merge
  - Require branches to be up to date before merging (strict mode)
  - Require pull-request reviews (0 approving reviews required)
  - Enforce rules for administrators (no bypass)

Status model:
  ENFORCED   — remote protection matches the expected contract
  DRIFTED    — remote protection exists but differs from the contract
  MISSING    — no branch protection rule present on ``main``
  DEGRADED   — unable to verify (missing admin scope, plan limitation, etc.)
"""

import json
import logging
import subprocess
from enum import Enum
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Expected policy (single source of truth)
# ---------------------------------------------------------------------------

EXPECTED_POLICY: Dict[str, Any] = {
    "required_status_checks": {
        "strict": True,
        "contexts": ["validate-gate"],
    },
    "enforce_admins": True,
    "required_pull_request_reviews": {
        "required_approving_review_count": 0,
    },
    "restrictions": None,
}

BRANCH = "main"


class ProtectionStatus(Enum):
    """Result of verifying branch protection against the expected contract."""

    ENFORCED = "enforced"
    DRIFTED = "drifted"
    MISSING = "missing"
    DEGRADED = "degraded"


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_branch_protection(repo: str) -> Tuple[ProtectionStatus, List[str]]:
    """Check live GitHub branch protection against the expected contract.

    Returns ``(status, drift_details)`` where *drift_details* is a list of
    human-readable strings explaining each mismatch (empty when ENFORCED).
    """
    try:
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{repo}/branches/{BRANCH}/protection",
                "--jq", ".",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return ProtectionStatus.DEGRADED, [
            "gh CLI not available or request timed out"
        ]

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Not Found" in stderr:
            return ProtectionStatus.MISSING, [
                "No branch protection rule found on main"
            ]
        if "403" in stderr or "Must have admin" in stderr:
            return ProtectionStatus.DEGRADED, [
                "Insufficient permissions (requires admin access or GitHub Pro/Team)"
            ]
        return ProtectionStatus.DEGRADED, [
            f"GitHub API error: {stderr[:120]}"
        ]

    try:
        actual = json.loads(result.stdout)
    except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return ProtectionStatus.DEGRADED, [
            "Could not parse GitHub API response"
        ]

    return _compare_policy(actual)


def _compare_policy(
    actual: Dict[str, Any],
) -> Tuple[ProtectionStatus, List[str]]:
    """Compare actual GitHub protection response against EXPECTED_POLICY."""
    drifts: List[str] = []

    # 1. Required status checks
    actual_checks = actual.get("required_status_checks") or {}
    expected_checks = EXPECTED_POLICY["required_status_checks"]

    actual_strict = actual_checks.get("strict", False)
    if actual_strict != expected_checks["strict"]:
        drifts.append(
            f"required_status_checks.strict: "
            f"expected {expected_checks['strict']}, got {actual_strict}"
        )

    actual_contexts = _extract_contexts(actual_checks)
    expected_contexts = set(expected_checks["contexts"])
    missing_contexts = expected_contexts - actual_contexts
    if missing_contexts:
        drifts.append(
            f"required_status_checks.contexts: "
            f"missing {sorted(missing_contexts)}"
        )

    # 2. Enforce admins
    enforce_admins_obj = actual.get("enforce_admins") or {}
    actual_enforce = enforce_admins_obj.get("enabled", False)
    if actual_enforce != EXPECTED_POLICY["enforce_admins"]:
        drifts.append(
            f"enforce_admins: expected {EXPECTED_POLICY['enforce_admins']}, "
            f"got {actual_enforce}"
        )

    # 3. Required pull request reviews
    actual_pr = actual.get("required_pull_request_reviews") or {}
    expected_pr = EXPECTED_POLICY["required_pull_request_reviews"]
    actual_count = actual_pr.get("required_approving_review_count")
    if actual_count is None:
        drifts.append(
            "required_pull_request_reviews: not configured"
        )
    elif actual_count != expected_pr["required_approving_review_count"]:
        drifts.append(
            f"required_pull_request_reviews.required_approving_review_count: "
            f"expected {expected_pr['required_approving_review_count']}, "
            f"got {actual_count}"
        )

    if drifts:
        return ProtectionStatus.DRIFTED, drifts

    return ProtectionStatus.ENFORCED, []


def _extract_contexts(checks: Dict[str, Any]) -> set:
    """Extract status check context names from the API response.

    GitHub returns contexts in two different shapes depending on the API
    version and how rules were configured:
      - ``checks`` array of ``{"context": "name", ...}`` objects
      - ``contexts`` flat array of strings (legacy)
    """
    contexts: set = set()
    for check in checks.get("checks", []):
        ctx = check.get("context")
        if ctx:
            contexts.add(ctx)
    for ctx in checks.get("contexts", []):
        if isinstance(ctx, str):
            contexts.add(ctx)
    return contexts


# ---------------------------------------------------------------------------
# Application (delegates to gh api PUT — mirrors original initializer logic)
# ---------------------------------------------------------------------------


def apply_branch_protection(repo: str) -> bool:
    """Apply the expected branch protection policy to *repo*.

    Returns True on success, False otherwise.  Prints a status line for
    interactive callers (same contract as the original initializer helper).
    """
    try:
        payload = json.dumps(EXPECTED_POLICY)
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{repo}/branches/{BRANCH}/protection",
                "--method", "PUT",
                "--input", "-",
            ],
            input=payload,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            print(
                "  Branch protection: main "
                "(require validate check, require PR, enforce admins)"
            )
            return True
        stderr = result.stderr.strip()
        if "Not Found" in stderr or "403" in stderr:
            print(
                "  Branch protection: SKIPPED "
                "(requires admin access or GitHub Pro)"
            )
        else:
            print(f"  Branch protection: FAILED ({stderr[:80]})")
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        print("  Branch protection: SKIPPED (timeout or gh not available)")
        return False


def apply_and_verify(repo: str) -> Tuple[ProtectionStatus, List[str]]:
    """Apply branch protection, then verify the result.

    Returns the verification outcome so callers can report drift or
    degraded mode even after a successful application attempt.
    """
    applied = apply_branch_protection(repo)
    if not applied:
        # If we couldn't apply, still try to verify (maybe it was already set)
        return verify_branch_protection(repo)
    return verify_branch_protection(repo)
