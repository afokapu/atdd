"""
PR base-branch validator (issue #477).

Phase 2 of the orphan-merge guard. Phase 1 (CLI) is at
``src/atdd/coach/commands/pr.py``: it rejects ``atdd pr <N> --base <X>``
when ``X`` is not the repo default. But agents that bypass ``atdd pr``
and run ``gh pr create`` directly (the lived case for #475) can still
land a PR on a sibling-PR's branch — when that branch is deleted, the
merge orphans onto a phantom ref invisible to ``git log main``.

This validator catches that path. It calls ``gh pr list --state open
--json number,baseRefName,headRefName`` and emits one
``Violation(rule_id="coach.pr.base-must-be-default-branch")`` per open
PR whose ``baseRefName`` ≠ resolved default branch.

Convention: ``src/atdd/coach/conventions/rule-id.convention.yaml``
            (rule ``coach.pr.base-must-be-default-branch``).

Run: ``atdd validate coach``
"""
from __future__ import annotations

import json
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

pytestmark = [pytest.mark.coach, pytest.mark.github_api]

REPO_ROOT = find_repo_root()

_RULE = bind_rule("coach.pr.base-must-be-default-branch")

_VALIDATOR_ID = "pr_base_branch"


def _fetch_open_prs(repo_root: Path) -> List[dict]:
    """Return ``[{number, baseRefName, headRefName}, ...]`` for every open PR."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "open",
             "--json", "number,baseRefName,headRefName"],
            capture_output=True, text=True, timeout=30,
            cwd=repo_root,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logging.getLogger(__name__).warning(
            "gh pr list failed: %s",
            exc,
            extra={"error": str(exc)},
        )
        return []
    if result.returncode != 0:
        logging.getLogger(__name__).warning(
            "gh pr list returned %d: %s",
            result.returncode, result.stderr.strip(),
            extra={"stderr": result.stderr.strip(), "returncode": result.returncode},
        )
        return []
    try:
        data = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError as exc:
        logging.getLogger(__name__).warning(
            "gh pr list returned non-JSON: %s",
            exc,
            extra={"error": str(exc)},
        )
        return []
    return data or []


def evaluate_base_violations(
    open_prs: List[dict],
    default_branch: str,
) -> List[Violation]:
    """Pure evaluator: emit one Violation per PR with non-default base.

    Pure function — no GitHub access — so the helper-tests file can drive
    it from synthetic fixtures without hitting the network.
    """
    # #1802: a base that is the head of another OPEN pull request is a TRACKED
    # stack, not the phantom ref #477 guards against — its deletion is not
    # silent, and GitHub retargets the stack when the base PR merges. The data
    # was already fetched; only this set membership was missing. A base no open
    # PR is producing still violates, so the guard narrows rather than weakens.
    open_heads = {
        pr.get("headRefName") for pr in open_prs if pr.get("headRefName")
    }

    violations: List[Violation] = []
    for pr in open_prs:
        number = pr.get("number")
        base = pr.get("baseRefName")
        head = pr.get("headRefName")
        if not number or not base:
            continue
        if base == default_branch:
            continue
        if base in open_heads:
            continue
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"PR#{number}",
                detail=(
                    f"PR #{number} (head={head!r}) targets base "
                    f"{base!r} but the repo default branch is "
                    f"{default_branch!r}. Re-target via "
                    f"`gh pr edit {number} --base {default_branch}` "
                    f"or close + re-open with --force if the non-default "
                    f"base is intentional. See issue #477 + #475."
                ),
                fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
            )
        )
    return violations


def scan_open_prs_for_base_violations(
    repo_root: Optional[Path] = None,
) -> List[Violation]:
    """End-to-end scanner: fetch PRs, resolve default, emit Violations."""
    root = repo_root or REPO_ROOT
    default_branch = resolve_default_branch(root)
    open_prs = _fetch_open_prs(root)
    return evaluate_base_violations(open_prs, default_branch)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_every_open_pr_targets_default_branch():
    """
    SPEC: ``rule-id.convention.yaml::rules[coach.pr.base-must-be-default-branch]``.

    Given:  Every open PR returned by ``gh pr list --state open``.
    When:   Comparing ``baseRefName`` against the resolved default branch.
    Then:   No PR targets a non-default base. Mistargeted PRs surface as
            structured ``Violation`` records the disposition gate fails on.
    """
    violations = scan_open_prs_for_base_violations(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=violations,
    )
