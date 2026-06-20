# Acceptance: acc:govern-lifecycle:E003-INTEGRATION-002-coach-validator-fires-on-green-label-closes
# Acceptance: acc:govern-lifecycle:E003-INTEGRATION-003-pr-merge-passes-when-no-closes-reference
"""
coach.pr.merge-blocks-on-pre-smoke-close validator (issue #681).

Scans open PRs via PRManager and emits one structured Violation per PR
that auto-closes an ATDD issue still at a pre-SMOKE phase (RED/GREEN —
also INIT/PLANNED defensively).

Strict disposition — bypass forbidden; no inline suppression. The 2026-
05-13 substrate-asymmetry incident shipped 8 PRs whose ``Closes #N`` fired
at atdd:GREEN, skipping SMOKE+REFACTOR. This rule mirrors the tester-side
TESTER-SMOKE-PRES-001 pattern in coach.

Convention: ``src/atdd/coach/conventions/pr.convention.yaml``
            (rule ``coach.pr.merge-blocks-on-pre-smoke-close``).

Run: ``atdd validate coach``
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, List, Optional, Sequence

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.coach, pytest.mark.github_api]


_RULE = bind_rule("coach.pr.merge-blocks-on-pre-smoke-close")
_VALIDATOR_ID = "pr_merge_blocks_pre_smoke_close"

# Phases where an auto-closing PR must NOT merge (mirrors phase_labels.merge_blocked
# in pr.convention.yaml). INIT/PLANNED are included defensively — those phases
# should not have a code PR open against them, and if one exists with a
# Closes #N, the same lifecycle gap applies.
_BLOCKED_PHASES = frozenset({"INIT", "PLANNED", "RED", "GREEN"})

# Strategies that prove the PR will auto-close the linked issue on merge.
# These are the four strategies PRManager.resolve_linked_issue tries; only
# the first two ("api" = closingIssuesReferences, "body" = Closes/Fixes/
# Resolves keyword in body) actually trigger GitHub's auto-close. The
# "manifest" and "title" strategies are weaker inference — they identify a
# linked issue but DO NOT fire auto-close.
_AUTO_CLOSING_STRATEGIES = frozenset({"api", "body"})


REPO_ROOT = find_repo_root()


def evaluate_pr_merge_violations(
    resolutions: Sequence[dict],
) -> List[Violation]:
    """Pure evaluator: emit one Violation per PR resolution whose phase is blocked.

    Args:
        resolutions: Sequence of dicts shaped like the return value of
            ``PRManager.resolve_linked_issue`` but with one added key:
            ``pr_number`` (since ``resolve_linked_issue`` doesn't echo it).

    Pure function — no GitHub access — so helper tests can drive it from
    synthetic fixtures without hitting the network.
    """
    violations: List[Violation] = []
    for entry in resolutions:
        if entry is None:
            continue
        pr_number = entry.get("pr_number")
        issue_number = entry.get("issue_number")
        phase = entry.get("phase_label")
        strategy = entry.get("strategy")
        if not pr_number or not issue_number or not phase:
            continue
        if strategy not in _AUTO_CLOSING_STRATEGIES:
            # Weak linkage (manifest/title) does not fire GitHub auto-close,
            # so the lifecycle gap is not realized on merge.
            continue
        if phase not in _BLOCKED_PHASES:
            continue

        detail = (
            f"PR #{pr_number} → issue #{issue_number} (phase=atdd:{phase}) "
            f"auto-closes via strategy={strategy!r} but the issue has not "
            f"transitioned through SMOKE+REFACTOR. Merging this PR would "
            f"fire GitHub's auto-close before the lifecycle reaches SMOKE. "
            f"Drive the issue forward: "
            f"`atdd issue {issue_number} --status SMOKE` then "
            f"`atdd issue {issue_number} --status REFACTOR`, or remove the "
            f"Closes/Fixes/Resolves keyword from the PR body if this PR is "
            f"a partial step. See issue #681."
        )
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"PR#{pr_number}:0",
                detail=detail,
                fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
            )
        )
        logging.getLogger(__name__).error(
            "%s: PR #%d auto-closes issue #%d at atdd:%s (strategy=%s)",
            _RULE.rule_id, pr_number, issue_number, phase, strategy,
            extra={
                "pr": pr_number,
                "issue": issue_number,
                "phase": phase,
                "strategy": strategy,
                "rule_id": _RULE.rule_id,
            },
        )
    return violations


def scan_open_prs_for_pre_smoke_close(
    repo_root: Optional[Path] = None,
) -> List[Violation]:
    """End-to-end scanner: fetch open PRs, resolve linked issues, emit Violations."""
    root = repo_root or REPO_ROOT
    mgr = PRManager(target_dir=root)
    open_prs = mgr.fetch_open_prs()

    resolutions: List[dict] = []
    for pr in open_prs:
        pr_number = pr.get("number")
        if not pr_number:
            continue
        res = mgr.resolve_linked_issue(pr_number)
        if res is None:
            continue
        # PRManager.resolve_linked_issue does not echo the PR number; add it
        # so the evaluator can build a Violation location without re-querying.
        res = dict(res)
        res["pr_number"] = pr_number
        resolutions.append(res)

    return evaluate_pr_merge_violations(resolutions)


# ---------------------------------------------------------------------------
# PR-under-test scoping (WMBT E056)
# ---------------------------------------------------------------------------


def _current_pr_number(repo_root: Optional[Path] = None) -> Optional[int]:
    """Resolve the PR currently under test from CI context.

    Order: ``ATDD_PR_NUMBER`` / ``PR_NUMBER`` env → ``GITHUB_REF`` of the form
    ``refs/pull/<N>/merge`` (GitHub Actions pull_request event) → the current
    branch's open PR via ``PRManager``. Returns None when none resolves (e.g. a
    local repo-health run), in which case the gate stays repo-wide for back-compat.
    """
    raise NotImplementedError("E056: resolve the PR under test (GREEN)")


def select_blocking_violations(
    violations: Sequence[Violation], current_pr: Optional[int]
) -> List[Violation]:
    """Select the violations that should FAIL the strict gate on this CI run.

    With a resolved ``current_pr``, only that PR's violation blocks (so an innocent
    PR is not failed by other PRs' offenses, while an offending PR is still blocked
    on its own CI). With no current PR (local repo-health), all violations block
    (repo-wide back-compat). Non-current offenders are still returned-to-caller
    nowhere here — the caller logs them via the scan; this only narrows what blocks.
    """
    raise NotImplementedError("E056: scope blocking violations to the PR under test (GREEN)")


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_no_open_pr_closes_an_issue_in_pre_smoke_phase():
    """
    SPEC: ``pr.convention.yaml::rules[coach.pr.merge-blocks-on-pre-smoke-close]``.

    Given:  Every open PR returned by ``gh pr list --state open`` that has
            an auto-closing reference (Closes/Fixes/Resolves keyword OR a
            GraphQL ``closingIssuesReferences`` entry) to an ATDD issue.
    When:   Comparing the linked issue's atdd:<PHASE> label against the
            merge-eligibility set {SMOKE, REFACTOR, COMPLETE}.
    Then:   No open PR auto-closes an issue still at atdd:RED or atdd:GREEN
            (or INIT/PLANNED). PRs that violate this gap surface as
            structured ``Violation`` records the disposition gate fails on.
            Strict disposition — bypass forbidden.
    """
    violations = scan_open_prs_for_pre_smoke_close(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=violations,
    )
