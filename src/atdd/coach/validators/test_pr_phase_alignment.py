"""
PR phase alignment validation.

Purpose: Verify that PR content matches the linked issue's ATDD phase label.
A PR that merges code changes while the linked issue is still at INIT or
PLANNED indicates skipped lifecycle phases (the incident pattern from #256).

Phase mapping:
    INIT / PLANNED  → expect plan files, contracts, WMBT definitions only
    RED             → expect test files only
    GREEN+          → expect code changes

SPEC-COACH-PRGATE-0002: PR merging code changes warns if linked issue is
at INIT or PLANNED.

Run: atdd validate coach
"""

import logging
from pathlib import Path
from typing import List, Sequence, Tuple

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.utils.repo import find_repo_root
from atdd.coder.baselines.ratchet import RatchetBaseline

pytestmark = [pytest.mark.platform, pytest.mark.github_api]

REPO_ROOT = find_repo_root()

# Baseline path for coach validators
COACH_BASELINE_PATH = REPO_ROOT / ".atdd" / "baselines" / "coach.yaml"

# File path patterns that indicate code changes (not just planner artifacts)
_CODE_PATH_PREFIXES = (
    "python/",
    "web/src/",
    "supabase/functions/",
    "packages/",
    "supabase/migrations/",
)

# File path patterns that indicate test files
_TEST_PATH_PATTERNS = (
    "/tests/",
    "/test_",
    ".test.",
    ".spec.",
)

# File path patterns that indicate planner-only artifacts
_PLAN_PATH_PREFIXES = (
    "plan/",
    "contracts/",
    "telemetry/",
    ".atdd/",
)

# Phases where code changes in a PR are unexpected
_EARLY_PHASES = frozenset({"INIT", "PLANNED"})


def _classify_changed_files(files: List[str]) -> dict:
    """Classify PR changed files into code, test, and plan categories."""
    result = {"code": [], "test": [], "plan": [], "other": []}
    for f in files:
        if any(pat in f for pat in _TEST_PATH_PATTERNS):
            result["test"].append(f)
        elif any(f.startswith(pfx) for pfx in _CODE_PATH_PREFIXES):
            result["code"].append(f)
        elif any(f.startswith(pfx) for pfx in _PLAN_PATH_PREFIXES):
            result["plan"].append(f)
        else:
            result["other"].append(f)
    return result


def scan_pr_phase_alignment(repo_root: Path) -> Tuple[int, Sequence]:
    """Scan open PRs for phase alignment violations.

    Returns (violation_count, violation_messages) for ratchet baseline.
    """
    mgr = PRManager(target_dir=repo_root)
    open_prs = mgr.fetch_open_prs()
    violations: List[str] = []

    for pr in open_prs:
        pr_number = pr["number"]
        resolution = mgr.resolve_linked_issue(pr_number)
        if resolution is None:
            continue

        phase = resolution["phase_label"]
        if phase is None or phase not in _EARLY_PHASES:
            continue

        changed_files = mgr.fetch_pr_changed_files(pr_number)
        if not changed_files:
            continue

        classified = _classify_changed_files(changed_files)

        if classified["code"]:
            code_sample = classified["code"][:3]
            violations.append(
                f"PR #{pr_number} → issue #{resolution['issue_number']} "
                f"(phase={phase}): {len(classified['code'])} code file(s) "
                f"changed — expected plan/contract artifacts only at {phase}. "
                f"Files: {', '.join(code_sample)}"
                + (f" ... +{len(classified['code']) - 3} more"
                   if len(classified["code"]) > 3 else "")
            )
            logging.getLogger(__name__).warning(
                "SPEC-COACH-PRGATE-0002: PR #%d has code changes but "
                "issue #%d is at %s",
                pr_number, resolution["issue_number"], phase,
                extra={
                    "pr": pr_number,
                    "issue": resolution["issue_number"],
                    "phase": phase,
                    "code_files": len(classified["code"]),
                },
            )

    return len(violations), violations


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_pr_phase_alignment():
    """
    SPEC-COACH-PRGATE-0002: PR content must align with linked issue phase.

    Given: Open PRs with linked ATDD issues
    When: Checking PR changed files vs issue phase label
    Then: PRs with code changes for INIT/PLANNED issues are flagged

    Ratchet baseline: violations must not exceed recorded baseline (Category A).
    """
    baseline = RatchetBaseline(COACH_BASELINE_PATH)
    count, violations = scan_pr_phase_alignment(REPO_ROOT)

    baseline.assert_no_regression(
        validator_id="pr_phase_alignment",
        current_count=count,
        violations=violations,
    )
