# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E056-UNIT-001-failure-scoped-to-pr-under-test
# Acceptance: acc:govern-lifecycle:E056-UNIT-001-failure-scoped-to-pr-under-test
# WMBT: wmbt:govern-lifecycle:E056
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E056-UNIT-001 — the strict pre-smoke-close gate fails only on the PR-under-test's
own violation: an offending current PR is blocked; a clean current PR is NOT blocked
even when other PRs are offending; with no current PR the behavior is repo-wide. The
current-PR resolver derives the PR number from GITHUB_REF and PR_NUMBER."""
from __future__ import annotations

import pytest

from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod
from atdd.coach.validators._violation import Violation


def _v(pr_number: int) -> Violation:
    return Violation(
        rule_id="coach.pr.merge-blocks-on-pre-smoke-close",
        severity=4,
        location=f"PR#{pr_number}:0",
        detail=f"PR #{pr_number} offends",
    )


# --- select_blocking_violations (pure scoping) ------------------------------

def test_clean_current_pr_not_blocked_by_other_offenders() -> None:
    violations = [_v(1161), _v(1163)]  # other PRs offend; current PR 1160 is clean
    blocking = mod.select_blocking_violations(violations, current_pr=1160)
    assert blocking == []


def test_offending_current_pr_is_blocked() -> None:
    violations = [_v(1161), _v(1163)]
    blocking = mod.select_blocking_violations(violations, current_pr=1161)
    assert [v.location for v in blocking] == ["PR#1161:0"]


def test_no_current_pr_blocks_repo_wide() -> None:
    violations = [_v(1161), _v(1163)]
    blocking = mod.select_blocking_violations(violations, current_pr=None)
    assert blocking == violations


# --- _current_pr_number (CI-context resolution) -----------------------------

def test_resolves_from_github_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATDD_PR_NUMBER", raising=False)
    monkeypatch.delenv("PR_NUMBER", raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1160/merge")
    assert mod._current_pr_number() == 1160


def test_resolves_from_pr_number_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REF", raising=False)
    monkeypatch.setenv("PR_NUMBER", "1166")
    assert mod._current_pr_number() == 1166


def test_returns_none_when_unresolvable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATDD_PR_NUMBER", raising=False)
    monkeypatch.delenv("PR_NUMBER", raising=False)
    monkeypatch.delenv("GITHUB_REF", raising=False)
    # No CI context and no branch PR resolvable -> None (repo-wide fallback).
    monkeypatch.setattr(mod, "_branch_pr_number", lambda repo_root=None: None, raising=False)
    assert mod._current_pr_number() is None
