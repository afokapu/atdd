# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E062-UNIT-003-closes-keyword-gate-scopes-to-pr-under-validation
# Acceptance: acc:govern-lifecycle:E062-UNIT-003-closes-keyword-gate-scopes-to-pr-under-validation
# WMBT: wmbt:govern-lifecycle:E062
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E062-UNIT-003 — the twin gate scopes to the PR under validation too.

``coach.pr.closes-keyword-discipline`` is strict (sev=4) and scans every open PR with
no scoping whatsoever — the same repo-wide blast radius as the pre-SMOKE gate, merely
latent because no open PR happens to violate it today. It gets the same treatment.

Its violation locations are ``PR#<n>:body`` / ``PR#<n>:commit:<sha>``, not the
pre-SMOKE gate's ``PR#<n>:0``, so the shared selector must key on the ``PR#<n>:``
prefix rather than on an exact location string.
"""
from __future__ import annotations

from atdd.coach.validators import test_pr_closes_keyword_discipline as mod
from atdd.coach.validators._violation import Violation


def _violation(pr_number: int, suffix: str) -> Violation:
    return Violation(
        rule_id="coach.pr.closes-keyword-discipline",
        severity=4,
        location=f"PR#{pr_number}:{suffix}",
        detail=f"PR #{pr_number} auto-closes without an affirmative body Closes",
    )


def test_clean_current_pr_not_blocked_by_another_prs_offense() -> None:
    violations = [_violation(1461, "body"), _violation(1456, "commit:deadbeef")]
    assert mod.select_blocking_violations(violations, current_pr=1479) == []


def test_offending_current_pr_is_still_blocked_on_its_own_run() -> None:
    violations = [_violation(1461, "body"), _violation(1456, "commit:deadbeef")]
    blocking = mod.select_blocking_violations(violations, current_pr=1461)
    assert [v.location for v in blocking] == ["PR#1461:body"]


def test_commit_located_violation_is_matched_by_its_pr_prefix() -> None:
    """The commit-injected form must scope by PR too — not fall through unmatched."""
    violations = [_violation(1456, "commit:deadbeef")]
    blocking = mod.select_blocking_violations(violations, current_pr=1456)
    assert [v.location for v in blocking] == ["PR#1456:commit:deadbeef"]
