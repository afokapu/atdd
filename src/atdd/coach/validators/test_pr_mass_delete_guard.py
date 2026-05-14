# Acceptance: acc:integration-hardening:C004-UNIT-001-validator-fails-on-files-over-threshold
# Acceptance: acc:integration-hardening:C004-UNIT-002-validator-fails-on-lines-over-threshold
# Acceptance: acc:integration-hardening:C004-UNIT-003-validator-allows-decom-prefix
# Acceptance: acc:integration-hardening:C004-UNIT-004-validator-allows-mass-delete-approved-token
# Acceptance: acc:integration-hardening:C004-INTEGRATION-001-replay-wave12-disaster-signature
# Acceptance: acc:integration-hardening:C004-SMOKE-001-validator-via-real-gh-pr-list-against-repo
"""
CI mass-delete guard validator (#629 Layer 3).

Server-side last-resort backstop for the Wave 12 contamination class.
PRs #625 and #627 each accidentally deleted 1,277 files / 220,000 lines
due to a worktree with core.bare=true. Layer 1 (pre-push) and Layer 2
(commit-msg) block at the laptop; this CI guard catches bypass via
ATDD_SKIP_MASSDELETE override or force-push.

A PR fails this guard when its diff deletes:
  - > 100 files, OR
  - > 10,000 lines

UNLESS an escape hatch is present:
  - PR title begins with: chore(decom, refactor(remove, or chore(archive)
  - Any commit message body contains the literal token [mass-delete-approved]

Convention: src/atdd/coach/conventions/rule-id.convention.yaml
            (rule coach.pr.mass-delete-guard)

WMBT: plan/integration_hardening/C004.yaml

Run: atdd validate coach
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.coach, pytest.mark.github_api]

REPO_ROOT = find_repo_root()

_RULE = bind_rule("coach.pr.mass-delete-guard")

_VALIDATOR_ID = "pr_mass_delete_guard"

# Thresholds — matching Wave 12 contamination class
_MAX_DELETED_FILES = 100
_MAX_DELETED_LINES = 10_000

# PR title prefixes that signal an intentional decommission
_DECOM_PREFIXES: Tuple[str, ...] = (
    "chore(decom",
    "refactor(remove",
    "chore(archive",
)

# Token that may appear in any commit body to approve a mass delete
_APPROVED_TOKEN = "[mass-delete-approved]"


# ---------------------------------------------------------------------------
# Pure evaluator (no GitHub access — drives unit tests directly)
# ---------------------------------------------------------------------------


def _has_escape_hatch(title: str, commit_bodies: List[str]) -> bool:
    """Return True if the PR carries an approved escape hatch."""
    if any(title.startswith(prefix) for prefix in _DECOM_PREFIXES):
        return True
    if any(_APPROVED_TOKEN in body for body in commit_bodies):
        return True
    return False


def evaluate_mass_delete_violations(
    pr_number: int,
    title: str,
    deleted_files: int,
    deleted_lines: int,
    commit_bodies: List[str],
) -> List[Violation]:
    """Pure evaluator: emit a Violation when mass-delete thresholds are exceeded.

    Args:
        pr_number: The GitHub PR number (used in location/detail).
        title: PR title string (checked for decom prefix escape hatch).
        deleted_files: Count of files with status 'removed' in the PR diff.
        deleted_lines: Total lines deleted across the PR diff.
        commit_bodies: List of commit message bodies for the PR.

    Returns:
        A list containing at most one Violation, or empty when the PR is safe.
    """
    if _has_escape_hatch(title, commit_bodies):
        return []

    exceeded: List[str] = []
    if deleted_files > _MAX_DELETED_FILES:
        exceeded.append(f"{deleted_files} deleted files (limit {_MAX_DELETED_FILES})")
    if deleted_lines > _MAX_DELETED_LINES:
        exceeded.append(f"{deleted_lines} deleted lines (limit {_MAX_DELETED_LINES})")

    if not exceeded:
        return []

    summary = " and ".join(exceeded)
    detail = (
        f"PR #{pr_number} ({title!r}): {summary}. "
        f"This matches the Wave 12 contamination signature. "
        f"Add a decommission title prefix (chore(decom:, refactor(remove:, "
        f"chore(archive:) or a commit body containing '{_APPROVED_TOKEN}' "
        f"to approve an intentional mass delete. See #629 Layer 3."
    )
    logging.getLogger(__name__).error(
        "%s: PR #%d exceeds mass-delete thresholds: %s",
        _RULE.rule_id, pr_number, summary,
        extra={
            "pr": pr_number,
            "deleted_files": deleted_files,
            "deleted_lines": deleted_lines,
            "rule_id": _RULE.rule_id,
        },
    )
    return [
        Violation(
            rule_id=_RULE.rule_id,
            severity=_RULE.severity,
            location=f"PR#{pr_number}:0",
            detail=detail,
        )
    ]


# ---------------------------------------------------------------------------
# GitHub I/O helpers
# ---------------------------------------------------------------------------


def _fetch_open_pr_numbers(repo_root: Path) -> List[int]:
    """Return a list of open PR numbers via gh pr list."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--json", "number"],
            capture_output=True, text=True, timeout=30,
            cwd=repo_root,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logging.getLogger(__name__).warning("gh pr list failed: %s", exc)
        return []
    if result.returncode != 0:
        logging.getLogger(__name__).warning(
            "gh pr list returned %d: %s", result.returncode, result.stderr.strip()
        )
        return []
    try:
        data = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError as exc:
        logging.getLogger(__name__).warning("gh pr list non-JSON: %s", exc)
        return []
    return [pr["number"] for pr in data if isinstance(pr.get("number"), int)]


def _fetch_pr_delete_stats(
    pr_number: int, repo_root: Path
) -> Optional[dict]:
    """Return {title, deleted_files, deleted_lines, commit_bodies} for one PR.

    Calls ``gh pr view <N> --json title,files,deletions,commits``.
    Returns None on error (validator stays quiet for unobtainable PRs).
    """
    try:
        result = subprocess.run(
            [
                "gh", "pr", "view", str(pr_number),
                "--json", "title,files,deletions,commits",
            ],
            capture_output=True, text=True, timeout=30,
            cwd=repo_root,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logging.getLogger(__name__).warning(
            "gh pr view %d failed: %s", pr_number, exc
        )
        return None
    if result.returncode != 0:
        logging.getLogger(__name__).warning(
            "gh pr view %d returned %d: %s",
            pr_number, result.returncode, result.stderr.strip(),
        )
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logging.getLogger(__name__).warning(
            "gh pr view %d non-JSON: %s", pr_number, exc
        )
        return None

    title = data.get("title", "")
    deleted_lines = data.get("deletions", 0) or 0
    files = data.get("files") or []
    deleted_files = sum(
        1 for f in files if f.get("status") == "removed"
    )
    commits = data.get("commits") or []
    commit_bodies = [
        c.get("messageBody", "") or c.get("message", "") or ""
        for c in commits
    ]
    return {
        "title": title,
        "deleted_files": deleted_files,
        "deleted_lines": deleted_lines,
        "commit_bodies": commit_bodies,
    }


def scan_open_prs_for_mass_delete(
    repo_root: Optional[Path] = None,
) -> List[Violation]:
    """End-to-end scanner: fetch open PRs, evaluate each, return violations."""
    root = repo_root or REPO_ROOT
    pr_numbers = _fetch_open_pr_numbers(root)
    violations: List[Violation] = []
    for number in pr_numbers:
        stats = _fetch_pr_delete_stats(number, root)
        if stats is None:
            continue
        violations.extend(
            evaluate_mass_delete_violations(
                pr_number=number,
                title=stats["title"],
                deleted_files=stats["deleted_files"],
                deleted_lines=stats["deleted_lines"],
                commit_bodies=stats["commit_bodies"],
            )
        )
    return violations


# ---------------------------------------------------------------------------
# Integration test (GitHub API — runs with atdd validate coach)
# ---------------------------------------------------------------------------


def test_no_open_pr_exceeds_mass_delete_thresholds():
    """
    coach.pr.mass-delete-guard: No open PR may exceed mass-delete thresholds
    without an approved escape hatch.

    Given:  All open PRs in the repo.
    When:   Checking each PR's deleted-file count and deleted-line count.
    Then:   PRs that delete >100 files or >10,000 lines fail unless the title
            begins with a decommission prefix or any commit body carries
            the [mass-delete-approved] token.
    """
    violations = scan_open_prs_for_mass_delete(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=violations,
    )


# ---------------------------------------------------------------------------
# Unit tests — pure evaluator, no GitHub access (acc: C004-UNIT-*)
# ---------------------------------------------------------------------------


def test_c004_unit_001_fails_on_files_over_threshold():
    """acc:integration-hardening:C004-UNIT-001 — files > 100 with no escape hatch."""
    violations = evaluate_mass_delete_violations(
        pr_number=999,
        title="feat: normal change",
        deleted_files=101,
        deleted_lines=0,
        commit_bodies=[],
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == "coach.pr.mass-delete-guard"
    assert "101" in v.detail
    assert "999" in v.location


def test_c004_unit_001_passes_below_threshold():
    """Exactly at the limit (100 files) is allowed."""
    violations = evaluate_mass_delete_violations(
        pr_number=1,
        title="feat: boundary check",
        deleted_files=100,
        deleted_lines=0,
        commit_bodies=[],
    )
    assert violations == []


def test_c004_unit_002_fails_on_lines_over_threshold():
    """acc:integration-hardening:C004-UNIT-002 — lines > 10000 with no escape hatch."""
    violations = evaluate_mass_delete_violations(
        pr_number=888,
        title="feat: normal",
        deleted_files=5,
        deleted_lines=10_001,
        commit_bodies=[],
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == "coach.pr.mass-delete-guard"
    assert "10001" in v.detail
    assert "888" in v.location


def test_c004_unit_002_passes_at_line_threshold():
    """Exactly 10,000 lines deleted is allowed."""
    violations = evaluate_mass_delete_violations(
        pr_number=2,
        title="feat: boundary",
        deleted_files=0,
        deleted_lines=10_000,
        commit_bodies=[],
    )
    assert violations == []


def test_c004_unit_003_allows_chore_decom_prefix():
    """acc:integration-hardening:C004-UNIT-003 — chore(decom prefix bypasses guard."""
    violations = evaluate_mass_delete_violations(
        pr_number=777,
        title="chore(decom): remove old wagon",
        deleted_files=500,
        deleted_lines=50_000,
        commit_bodies=[],
    )
    assert violations == []


def test_c004_unit_003_allows_refactor_remove_prefix():
    """acc:integration-hardening:C004-UNIT-003 — refactor(remove prefix bypasses guard."""
    violations = evaluate_mass_delete_violations(
        pr_number=776,
        title="refactor(remove): drop legacy code",
        deleted_files=500,
        deleted_lines=50_000,
        commit_bodies=[],
    )
    assert violations == []


def test_c004_unit_003_allows_chore_archive_prefix():
    """acc:integration-hardening:C004-UNIT-003 — chore(archive prefix bypasses guard."""
    violations = evaluate_mass_delete_violations(
        pr_number=775,
        title="chore(archive): archive unused module",
        deleted_files=500,
        deleted_lines=50_000,
        commit_bodies=[],
    )
    assert violations == []


def test_c004_unit_004_allows_mass_delete_approved_token():
    """acc:integration-hardening:C004-UNIT-004 — [mass-delete-approved] in commit body."""
    violations = evaluate_mass_delete_violations(
        pr_number=666,
        title="feat: normal work",
        deleted_files=200,
        deleted_lines=20_000,
        commit_bodies=[
            "first commit message",
            "second commit [mass-delete-approved] intentional cleanup",
        ],
    )
    assert violations == []


def test_c004_unit_004_token_must_be_exact():
    """Near-miss token does not count as escape hatch."""
    violations = evaluate_mass_delete_violations(
        pr_number=667,
        title="feat: normal",
        deleted_files=200,
        deleted_lines=20_000,
        commit_bodies=["mass-delete-approved (no brackets)"],
    )
    assert len(violations) == 1


def test_c004_integration_001_wave12_disaster_signature():
    """acc:integration-hardening:C004-INTEGRATION-001 — exact Wave 12 signature caught."""
    violations = evaluate_mass_delete_violations(
        pr_number=625,
        title="feat(atdd): some feature work",
        deleted_files=1277,
        deleted_lines=220_000,
        commit_bodies=["normal commit message without any token"],
    )
    assert len(violations) >= 1
    assert violations[0].rule_id == "coach.pr.mass-delete-guard"


def test_severity_is_four():
    """Rule severity must be 4 (correctness/safety class)."""
    assert _RULE.severity == 4


def test_both_thresholds_exceeded_emits_single_violation():
    """When both files and lines are over threshold, emit exactly one Violation."""
    violations = evaluate_mass_delete_violations(
        pr_number=500,
        title="feat: normal",
        deleted_files=200,
        deleted_lines=50_000,
        commit_bodies=[],
    )
    assert len(violations) == 1


def test_zero_deletes_passes():
    """PR with zero deletes is always safe."""
    violations = evaluate_mass_delete_violations(
        pr_number=1,
        title="feat: add new file",
        deleted_files=0,
        deleted_lines=0,
        commit_bodies=[],
    )
    assert violations == []
