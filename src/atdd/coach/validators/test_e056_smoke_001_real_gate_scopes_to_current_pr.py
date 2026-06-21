# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E056-SMOKE-001-real-gate-scopes-to-current-pr
# Acceptance: acc:govern-lifecycle:E056-SMOKE-001-real-gate-scopes-to-current-pr
# WMBT: wmbt:govern-lifecycle:E056
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E056-SMOKE-001 — the REAL coach.pr.merge-blocks-on-pre-smoke-close validator
module, driven by a real CI environment (GITHUB_REF), scopes its strict failure to
the PR under test: a clean current PR passes the real disposition gate even though
an offending PR is present in the scan, and the offender's violation is still
produced for visibility.

Real infra: the real validator module functions (evaluate_pr_merge_violations,
_current_pr_number reading real env, select_blocking_violations) and the real
assert_disposition_satisfied gate — no mocks, no network."""
from __future__ import annotations

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod


@pytest.mark.smoke
def test_real_gate_scopes_failure_to_current_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    # Real CI context: the PR under test is #1160 (clean); an unrelated PR #1161
    # auto-closes an issue still at atdd:GREEN (offender).
    monkeypatch.delenv("ATDD_PR_NUMBER", raising=False)
    monkeypatch.delenv("PR_NUMBER", raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1160/merge")

    resolutions = [
        {"pr_number": 1161, "issue_number": 1085, "phase_label": "GREEN", "strategy": "api"},
    ]

    # Real evaluator produces the offender's violation (visibility preserved).
    all_violations = mod.evaluate_pr_merge_violations(resolutions)
    assert [v.location for v in all_violations] == ["PR#1161:0"]

    # Real env resolution picks the PR under test; real scoping narrows the gate.
    current_pr = mod._current_pr_number()
    assert current_pr == 1160
    blocking = mod.select_blocking_violations(all_violations, current_pr)
    assert blocking == []

    # The real disposition gate passes for the clean current PR (no raise).
    assert_disposition_satisfied(validator_id=mod._VALIDATOR_ID, violations=blocking)


@pytest.mark.smoke
def test_real_gate_blocks_offending_current_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    # When the offender IS the PR under test, the real gate still fails (safety).
    monkeypatch.delenv("ATDD_PR_NUMBER", raising=False)
    monkeypatch.delenv("PR_NUMBER", raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1161/merge")

    resolutions = [
        {"pr_number": 1161, "issue_number": 1085, "phase_label": "GREEN", "strategy": "api"},
    ]
    all_violations = mod.evaluate_pr_merge_violations(resolutions)
    blocking = mod.select_blocking_violations(all_violations, mod._current_pr_number())

    # The offender IS the PR under test, so its violation is selected as blocking —
    # a non-empty strict violation set fails the real disposition gate (safety kept).
    assert [v.location for v in blocking] == ["PR#1161:0"]
    with pytest.raises(BaseException):
        assert_disposition_satisfied(validator_id=mod._VALIDATOR_ID, violations=blocking)
