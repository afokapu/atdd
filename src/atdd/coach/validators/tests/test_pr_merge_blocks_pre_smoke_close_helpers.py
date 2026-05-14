"""
Pure-evaluator unit tests for the coach PR-merge SMOKE-gate validator (#681).

Co-located with the other PR validator helper tests under
``src/atdd/coach/validators/tests/``. These tests exercise
``evaluate_pr_merge_violations`` directly with synthetic resolution
payloads — no network, no marker, no disposition-gate.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators._violation import Violation
from atdd.coach.validators.test_pr_merge_blocks_pre_smoke_close import (
    _AUTO_CLOSING_STRATEGIES,
    _BLOCKED_PHASES,
    _RULE,
    evaluate_pr_merge_violations,
)


def _resolution(
    pr_number: int = 1,
    issue_number: int = 100,
    phase_label: str = "GREEN",
    strategy: str = "body",
) -> dict:
    return {
        "pr_number": pr_number,
        "issue_number": issue_number,
        "phase_label": phase_label,
        "strategy": strategy,
    }


# ---------------------------------------------------------------------------
# Empty / null handling
# ---------------------------------------------------------------------------


def test_evaluate_returns_empty_on_no_resolutions():
    assert evaluate_pr_merge_violations([]) == []


def test_evaluate_skips_none_entries():
    assert evaluate_pr_merge_violations([None, None]) == []  # type: ignore[list-item]


def test_evaluate_skips_resolutions_missing_required_fields():
    """Defensive: malformed PRManager rows don't blow up the scanner."""
    bad_resolutions = [
        {"pr_number": None, "issue_number": 1, "phase_label": "GREEN", "strategy": "body"},
        {"pr_number": 1, "issue_number": None, "phase_label": "GREEN", "strategy": "body"},
        {"pr_number": 1, "issue_number": 1, "phase_label": None, "strategy": "body"},
    ]
    assert evaluate_pr_merge_violations(bad_resolutions) == []


# ---------------------------------------------------------------------------
# Blocked phases
# ---------------------------------------------------------------------------


def test_evaluate_emits_violation_for_green_with_body_close():
    """GREEN + body strategy: classic 2026-05-13 incident shape."""
    violations = evaluate_pr_merge_violations([
        _resolution(pr_number=681, issue_number=681, phase_label="GREEN", strategy="body"),
    ])

    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, Violation)
    assert v.rule_id == _RULE.rule_id == "coach.pr.merge-blocks-on-pre-smoke-close"
    assert v.severity == _RULE.severity
    assert "PR#681" in v.location
    assert "atdd:GREEN" in v.detail
    assert "681" in v.detail


def test_evaluate_emits_violation_for_red_with_api_close():
    """RED + api (closingIssuesReferences) strategy is also blocked."""
    violations = evaluate_pr_merge_violations([
        _resolution(pr_number=42, issue_number=42, phase_label="RED", strategy="api"),
    ])
    assert len(violations) == 1
    assert "atdd:RED" in violations[0].detail


def test_evaluate_emits_violations_for_init_and_planned_defensively():
    """INIT/PLANNED are defensively blocked (no PR should target those)."""
    for phase in ("INIT", "PLANNED"):
        violations = evaluate_pr_merge_violations([
            _resolution(pr_number=1, issue_number=1, phase_label=phase, strategy="body"),
        ])
        assert len(violations) == 1, f"phase={phase} should be blocked"


# ---------------------------------------------------------------------------
# Merge-allowed phases
# ---------------------------------------------------------------------------


def test_evaluate_quiet_for_smoke_phase():
    """SMOKE is the first merge-eligible phase."""
    violations = evaluate_pr_merge_violations([
        _resolution(phase_label="SMOKE", strategy="body"),
    ])
    assert violations == []


def test_evaluate_quiet_for_refactor_phase():
    violations = evaluate_pr_merge_violations([
        _resolution(phase_label="REFACTOR", strategy="body"),
    ])
    assert violations == []


def test_evaluate_quiet_for_complete_phase():
    violations = evaluate_pr_merge_violations([
        _resolution(phase_label="COMPLETE", strategy="body"),
    ])
    assert violations == []


# ---------------------------------------------------------------------------
# Strategy gating
# ---------------------------------------------------------------------------


def test_evaluate_quiet_for_weak_manifest_strategy_even_at_green():
    """Manifest-based linkage doesn't fire GitHub auto-close on merge."""
    violations = evaluate_pr_merge_violations([
        _resolution(phase_label="GREEN", strategy="manifest"),
    ])
    assert violations == []


def test_evaluate_quiet_for_weak_title_strategy_even_at_green():
    """Title-regex linkage (`#N` in the PR title) doesn't fire auto-close."""
    violations = evaluate_pr_merge_violations([
        _resolution(phase_label="GREEN", strategy="title"),
    ])
    assert violations == []


# ---------------------------------------------------------------------------
# Multi-PR
# ---------------------------------------------------------------------------


def test_evaluate_emits_one_violation_per_offending_pr():
    """Mix of clean and offending PRs → one Violation per offender."""
    violations = evaluate_pr_merge_violations([
        _resolution(pr_number=1, phase_label="REFACTOR", strategy="body"),
        _resolution(pr_number=2, phase_label="GREEN", strategy="body"),
        _resolution(pr_number=3, phase_label="GREEN", strategy="manifest"),  # weak link, ignored
        _resolution(pr_number=4, phase_label="RED", strategy="api"),
    ])
    assert len(violations) == 2
    locations = {v.location for v in violations}
    assert "PR#2:0" in locations
    assert "PR#4:0" in locations


# ---------------------------------------------------------------------------
# Constants sanity (catches accidental constant drift)
# ---------------------------------------------------------------------------


def test_blocked_phases_are_pre_smoke():
    assert _BLOCKED_PHASES == frozenset({"INIT", "PLANNED", "RED", "GREEN"})


def test_auto_closing_strategies_are_api_and_body_only():
    assert _AUTO_CLOSING_STRATEGIES == frozenset({"api", "body"})
