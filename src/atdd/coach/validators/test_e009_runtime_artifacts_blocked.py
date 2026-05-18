# Acceptance: acc:govern-lifecycle:E009-UNIT-002-evaluator-emits-violation-on-runtime-path-in-diff
# Acceptance: acc:govern-lifecycle:E009-SMOKE-001-real-validate-coach-runs-runtime-guard

"""E009 — Validator: no .atdd/runtime/** paths in PR diff vs default branch.

Binds ``coach.pr.runtime-artifacts-blocked``.

Agents writing runtime state under .atdd/runtime/ and then running
``git add -A`` or ``git commit`` will accidentally commit ephemeral per-run
artifacts (session JSON, decisions.jsonl, validation logs) into the PR diff.
This validator fails atdd validate coach when the branch diff vs the default
branch adds or modifies any path matching ``.atdd/runtime/**``.

``evaluate_runtime_artifact_violations`` is a pure evaluator: it accepts a
list of changed file paths (strings) and returns a list of Violations. The
GitHub I/O helper ``_fetch_pr_changed_files`` retrieves the file set for
the current open PR via ``gh pr view``.

Phase RED: fails because coach.pr.runtime-artifacts-blocked is not in any
           convention file; bind_rule() raises RuleNotInRegistryError.
Phase GREEN: rule declared; evaluator wired; tests pass.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.coach]

REPO_ROOT = find_repo_root()

_RULE = bind_rule("coach.pr.runtime-artifacts-blocked")

_VALIDATOR_ID = "e009_runtime_artifacts_blocked"

_RUNTIME_PREFIX = ".atdd/runtime/"


# ---------------------------------------------------------------------------
# Pure evaluator
# ---------------------------------------------------------------------------


def evaluate_runtime_artifact_violations(
    changed_files: List[str],
    pr_number: Optional[int] = None,
) -> List[Violation]:
    """Return a Violation for each .atdd/runtime/** path in changed_files.

    Args:
        changed_files: File paths from the branch diff (relative to repo root).
        pr_number: Optional PR number for Violation location detail.

    Returns:
        One Violation per offending path, or [] when the diff is clean.
    """
    violations: List[Violation] = []
    for path in changed_files:
        if path.startswith(_RUNTIME_PREFIX) or ("/.atdd/runtime/" in path):
            location = f"PR#{pr_number}:{path}" if pr_number else path
            detail = (
                f"Path {path!r} is under .atdd/runtime/ and must not appear in "
                "a PR diff. .atdd/runtime/ is ephemeral per-run state — it must "
                "be fully gitignored. Add .atdd/runtime/ to .gitignore and run "
                "git rm --cached on any tracked files. (coach.pr.runtime-artifacts-blocked)"
            )
            logging.getLogger(__name__).error(
                "%s: runtime artifact in PR diff: %s",
                _RULE.rule_id,
                path,
                extra={"rule_id": _RULE.rule_id, "path": path},
            )
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=location,
                    detail=detail,
                )
            )
    return violations


# ---------------------------------------------------------------------------
# GitHub I/O helpers
# ---------------------------------------------------------------------------


def _fetch_pr_changed_files(repo_root: Path) -> Optional[dict]:
    """Return {pr_number, files} for the first open PR from the current branch.

    Returns None on error so the validator stays quiet for unobtainable PRs.
    """
    try:
        list_result = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--json", "number,headRefName"],
            capture_output=True, text=True, timeout=30,
            cwd=repo_root,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logging.getLogger(__name__).warning("gh pr list failed: %s", exc)
        return None
    if list_result.returncode != 0:
        logging.getLogger(__name__).warning(
            "gh pr list returned %d: %s", list_result.returncode, list_result.stderr.strip()
        )
        return None
    try:
        prs = json.loads(list_result.stdout) if list_result.stdout.strip() else []
    except json.JSONDecodeError as exc:
        logging.getLogger(__name__).warning("gh pr list non-JSON: %s", exc)
        return None

    # Get current branch
    try:
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=repo_root,
        )
        current_branch = branch_result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        current_branch = ""

    # Find PR for current branch, or fall back to any open PR
    pr_number = None
    for pr in prs:
        if pr.get("headRefName") == current_branch:
            pr_number = pr["number"]
            break
    if pr_number is None and prs:
        pr_number = prs[0]["number"]
    if pr_number is None:
        return None

    try:
        view_result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "number,files"],
            capture_output=True, text=True, timeout=30,
            cwd=repo_root,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logging.getLogger(__name__).warning("gh pr view %d failed: %s", pr_number, exc)
        return None
    if view_result.returncode != 0:
        logging.getLogger(__name__).warning(
            "gh pr view %d returned %d: %s",
            pr_number, view_result.returncode, view_result.stderr.strip(),
        )
        return None
    try:
        data = json.loads(view_result.stdout)
    except json.JSONDecodeError as exc:
        logging.getLogger(__name__).warning("gh pr view non-JSON: %s", exc)
        return None

    files = [f["path"] for f in data.get("files", []) if isinstance(f.get("path"), str)]
    return {"pr_number": data.get("number"), "files": files}


def _fetch_diff_files_via_git(repo_root: Path, default_branch: str) -> List[str]:
    """Return files changed vs the default branch using git diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{default_branch}...HEAD"],
            capture_output=True, text=True, timeout=30,
            cwd=repo_root,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# ---------------------------------------------------------------------------
# E007-UNIT-002 tests — pure evaluator
# ---------------------------------------------------------------------------


def test_evaluator_emits_violation_for_runtime_path() -> None:
    """Single .atdd/runtime/ path yields exactly one Violation."""
    violations = evaluate_runtime_artifact_violations(
        [".atdd/runtime/coach/decisions.jsonl"]
    )
    assert len(violations) == 1, (
        f"Expected 1 Violation for .atdd/runtime/ path, got {len(violations)}"
    )
    assert violations[0].rule_id == _RULE.rule_id


def test_evaluator_emits_one_violation_per_runtime_path() -> None:
    """Two .atdd/runtime/ paths yield two separate Violations."""
    paths = [
        ".atdd/runtime/coach/358/planner-358-e7620840.session.json",
        ".atdd/runtime/agents/planner-358-4956120b/events.jsonl",
    ]
    violations = evaluate_runtime_artifact_violations(paths)
    assert len(violations) == 2, (
        f"Expected 2 Violations for {len(paths)} runtime paths, got {len(violations)}"
    )


def test_evaluator_ignores_non_runtime_paths() -> None:
    """Non-.atdd/runtime/ paths produce no Violations."""
    violations = evaluate_runtime_artifact_violations(
        ["src/atdd/coach/validators/test_foo.py", "plan/govern_lifecycle/E007.yaml"]
    )
    assert violations == [], (
        f"Expected no Violations for non-runtime paths, got {violations}"
    )


def test_evaluator_mixed_diff_emits_violation_only_for_runtime() -> None:
    """Mixed diff: only the runtime path triggers a Violation."""
    violations = evaluate_runtime_artifact_violations(
        [
            "src/foo.py",
            ".atdd/runtime/coach/decisions.jsonl",
            "plan/bar.yaml",
        ]
    )
    assert len(violations) == 1
    assert ".atdd/runtime/" in violations[0].detail


def test_evaluator_empty_diff_is_clean() -> None:
    """Empty changed_files list yields no Violations."""
    assert evaluate_runtime_artifact_violations([]) == []


# ---------------------------------------------------------------------------
# E007-SMOKE-001 test — real atdd validate coach
# ---------------------------------------------------------------------------


@pytest.mark.coach
def test_real_validate_coach_passes_on_clean_branch() -> None:
    """The current branch diff must contain no .atdd/runtime/** paths.

    Acceptance: acc:govern-lifecycle:E009-SMOKE-001-real-validate-coach-runs-runtime-guard

    Uses git diff to get the list of files changed vs the default branch and
    asserts the evaluator returns no violations. This proves .atdd/runtime/ is
    fully gitignored and no runtime artifacts ride the current PR.
    """
    from atdd.coach.utils.default_branch import resolve_default_branch

    default_branch = resolve_default_branch(REPO_ROOT)
    changed_files = _fetch_diff_files_via_git(REPO_ROOT, default_branch)

    violations = evaluate_runtime_artifact_violations(changed_files)

    assert_disposition_satisfied(
        rule=_RULE,
        validator_id=_VALIDATOR_ID,
        violations=violations,
        suppressed=[],
    )
