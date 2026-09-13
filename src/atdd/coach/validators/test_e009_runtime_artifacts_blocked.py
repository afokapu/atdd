# Acceptance: acc:govern-lifecycle:E009-UNIT-002-evaluator-emits-violation-on-runtime-path-in-diff
# Acceptance: acc:govern-lifecycle:E009-SMOKE-001-real-validate-coach-runs-runtime-guard
# Acceptance: acc:govern-lifecycle:E009-UNIT-003-evaluator-covers-the-per-run-validation-receipt-it-already-prohibits

"""E009 — Validator: no .atdd/runtime/** paths in PR diff vs default branch.

Binds ``coach.pr.runtime-artifacts-blocked``.

Agents writing runtime state under .atdd/runtime/ and then running
``git add -A`` or ``git commit`` accidentally commit ephemeral per-run
artifacts (session JSON, decisions.jsonl, validation logs) into the PR diff.
This validator fails atdd validate coach when the branch diff vs the default
branch adds or modifies any path matching ``.atdd/runtime/**``.

``evaluate_runtime_artifact_violations`` is a pure evaluator: it accepts a
list of changed file paths (strings) and returns a list of Violations.
``_fetch_diff_files_via_git`` retrieves the added/modified file set (deletes
excluded via --diff-filter=d) from ``git diff origin/<default>...HEAD``.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

import pytest

from atdd.coach.utils.default_branch import resolve_default_branch
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.coach]

REPO_ROOT = find_repo_root()

_RULE = bind_rule("coach.pr.runtime-artifacts-blocked")

_VALIDATOR_ID = "e009_runtime_artifacts_blocked"

#: The per-run artifact trees this rule refuses in a delivery diff.
#:
#: `.atdd/runtime/` is the original E009 subject. The per-phase validation
#: receipts joined it once the rule's own statement was read as written: it names
#: "validation logs" as ephemeral per-run state, and a receipt rewritten by every
#: passing validate is exactly that — it was simply living outside the runtime
#: dir, where the evaluator could not see it.
#:
#: Deliberately NARROW under `.atdd/baselines/` — `lint_toolkit.yaml`,
#: `types_toolkit.yaml` and `four_tier_toolkit.yaml` share that directory and are
#: the OPPOSITE kind of file: curated lists of frozen findings that are each their
#: gate's floor. A bare `.atdd/baselines/` here would tell an author to untrack
#: them, and a ratchet with no baseline passes on any amount of new debt (#1580).
_PER_RUN_PREFIXES = (
    ".atdd/runtime/",
    ".atdd/baselines/validation/",
)


# ---------------------------------------------------------------------------
# Pure evaluator
# ---------------------------------------------------------------------------



def _matched_prefix(path: str) -> Optional[str]:
    """The per-run prefix *path* falls under, or ``None``.

    Matches an embedded occurrence too (``/.atdd/runtime/``), because a diff may
    name a path relative to a parent of the repo root.
    """
    for prefix in _PER_RUN_PREFIXES:
        if path.startswith(prefix) or f"/{prefix}" in path:
            return prefix
    return None


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
        prefix = _matched_prefix(path)
        if prefix is not None:
            location = f"PR#{pr_number}:{path}" if pr_number else path
            detail = (
                f"Path {path!r} is under {prefix} and must not appear in "
                f"a PR diff. {prefix} is ephemeral per-run state — it must "
                f"be fully gitignored. Add {prefix} to .gitignore and run "
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
# I/O helper
# ---------------------------------------------------------------------------


def _fetch_diff_files_via_git(repo_root: Path, default_branch: str) -> List[str]:
    """Return added/modified (not deleted) files vs the default branch.

    Uses --diff-filter=d to exclude deleted files — a deletion of a
    .atdd/runtime/ file is a clean-up action, not a violation.
    """
    try:
        result = subprocess.run(
            [
                "git", "diff",
                "--name-only",
                "--diff-filter=d",
                f"origin/{default_branch}...HEAD",
            ],
            capture_output=True, text=True, timeout=30,
            cwd=repo_root,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# ---------------------------------------------------------------------------
# E009-UNIT-002 tests — pure evaluator
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
        ["src/atdd/coach/validators/test_foo.py", "plan/govern_lifecycle/E009.yaml"]
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
# E009-SMOKE-001 test — real atdd validate coach
# ---------------------------------------------------------------------------


@pytest.mark.coach
def test_real_validate_coach_passes_on_clean_branch() -> None:
    """The current branch diff must contain no .atdd/runtime/** paths.

    Acceptance: acc:govern-lifecycle:E009-SMOKE-001-real-validate-coach-runs-runtime-guard

    Uses git diff to get the list of files changed vs the default branch and
    asserts the evaluator returns no violations. This proves .atdd/runtime/ is
    fully gitignored and no runtime artifacts ride the current PR.
    """
    default_branch = resolve_default_branch(REPO_ROOT)
    changed_files = _fetch_diff_files_via_git(REPO_ROOT, default_branch)

    violations = evaluate_runtime_artifact_violations(changed_files)

    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=violations,
    )


# ---------------------------------------------------------------------------
# E009-UNIT-003 tests — the rule's stated scope is the enforced scope
#
# `coach.execution.runtime-state-not-a-delivery-artifact` names "validation
# logs" as per-run state that must never enter a delivery diff, but the
# evaluator has only ever read `.atdd/runtime/`. A per-run validation receipt
# under `.atdd/baselines/validation/` is therefore prohibited by the statement
# and invisible to the enforcement. The third test is the one that keeps the
# widening honest: `.atdd/baselines/` also holds the curated ratchet baselines,
# which ARE delivery artifacts and must never be flagged.
# ---------------------------------------------------------------------------


def test_evaluator_emits_violation_for_validation_receipt_path() -> None:
    """A per-run validation receipt in the diff yields exactly one Violation."""
    violations = evaluate_runtime_artifact_violations(
        [".atdd/baselines/validation/planner.yaml"]
    )
    assert len(violations) == 1, (
        "Expected 1 Violation for a per-run validation receipt, got "
        f"{len(violations)} — the rule names 'validation logs' but the "
        "evaluator cannot see this path"
    )
    assert violations[0].rule_id == _RULE.rule_id


def test_evaluator_still_emits_for_runtime_path_after_widening() -> None:
    """Widening must not regress E009's original `.atdd/runtime/` coverage."""
    violations = evaluate_runtime_artifact_violations(
        [".atdd/runtime/coach/decisions.jsonl"]
    )
    assert len(violations) == 1
    assert violations[0].rule_id == _RULE.rule_id


def test_evaluator_never_flags_a_curated_ratchet_baseline() -> None:
    """`.atdd/baselines/*_toolkit.yaml` are tracked delivery artifacts.

    They are curated lists of frozen findings that decide a gate verdict — the
    opposite role to a derived receipt, in the same directory. Flagging one
    would tell an author to untrack the floor their ratchet stands on.
    """
    violations = evaluate_runtime_artifact_violations(
        [
            "src/foo.py",
            ".atdd/baselines/lint_toolkit.yaml",
            ".atdd/baselines/types_toolkit.yaml",
            ".atdd/baselines/four_tier_toolkit.yaml",
        ]
    )
    assert violations == [], (
        f"A curated ratchet baseline must never be flagged, got {violations}"
    )
