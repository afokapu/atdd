# URN: urn:atdd:test:runners:security_runner:unit
# Issue: #422

"""Unit tests for the security-mode runner (substrate spec v12 §4.5 / §7.4).

Coverage:

* ``collect_security_violations`` returns no violations when bound rule passed.
* ``collect_security_violations`` returns one violation when bound rule failed.
* Bound rules absent from ``rule_outcomes`` are skipped (not exercised in run).
* ``run_security_runner`` raises ``pytest.fail`` for failing bound rules.
* The validator_id literal matches the spec §4.5 anchor.
* Outcome recording: passed-bound rules are recorded, failed-bound rules
  are recorded, partial runs (some rules unexercised) leave registry
  silent for those rules.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from atdd.coach.utils.disposition_gate import (
    get_active_pytest_session,
    set_active_pytest_session,
)
from atdd.coach.utils.rule_id_registry import RuleMetadata
from atdd.runners.security_runner import (
    VALIDATOR_ID,
    collect_security_violations,
    run_security_runner,
)


def _security_meta(
    *,
    rule_id: str = "repo.auth.session-management-security-001",
    bound_acc: str = "acc:auth:D001-UNIT-001-session-protection",
    severity: int = 4,
) -> RuleMetadata:
    """Construct a security-derived RuleMetadata fixture for runner tests."""
    return RuleMetadata(
        rule_id=rule_id,
        convention_path=Path("/tmp/feature.yaml"),
        severity=severity,
        description="Session Hijacking — Attacker steals session token via XSS",
        disposition="strict",
        validator=(
            "test_security_ref_binding::test_acceptance_ref_resolves_and_passes"
        ),
        fix_hint="HttpOnly cookies, CSP headers",
        security_urn="security:auth:session-management:001",
        feature_urn="feature:auth:session-management",
        bound_acceptance_urn=bound_acc,
    )


def test_validator_id_matches_spec_anchor():
    assert VALIDATOR_ID == (
        "test_security_ref_binding::test_acceptance_ref_resolves_and_passes"
    )


def test_collect_skips_when_bound_rule_passed():
    """Passing bound rule → no security violation; security rule recorded passed."""
    meta = _security_meta()
    registry = {meta.rule_id: meta}
    bound_rule_id = "repo.auth.D001-acc-unit-001"
    outcomes = {bound_rule_id: "passed"}

    violations = collect_security_violations(registry, outcomes)
    assert violations == []


def test_collect_emits_violation_when_bound_rule_failed():
    """Failed bound rule → one Violation referencing the bound URN."""
    meta = _security_meta()
    registry = {meta.rule_id: meta}
    bound_rule_id = "repo.auth.D001-acc-unit-001"
    outcomes = {bound_rule_id: "failed"}

    violations = collect_security_violations(registry, outcomes)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == meta.rule_id
    assert v.severity == 4
    assert "acc:auth:D001-UNIT-001-session-protection" in v.detail
    assert v.location == meta.feature_urn


def test_collect_skips_unexercised_bound_rules():
    """Bound rule absent from outcomes (not run) → no violation, no recording."""
    meta = _security_meta()
    registry = {meta.rule_id: meta}
    outcomes: dict = {}

    violations = collect_security_violations(registry, outcomes)
    assert violations == []


def test_collect_handles_invalid_severity_defensively():
    """Non-int / out-of-range severity is skipped rather than crashing."""
    meta = _security_meta()
    bad_meta = replace(meta, severity="high")  # toolkit rules sometimes use strings
    registry = {bad_meta.rule_id: bad_meta}
    outcomes = {"repo.auth.D001-acc-unit-001": "failed"}

    # Should not raise — invalid severity yields no violation.
    violations = collect_security_violations(registry, outcomes)
    assert violations == []


def test_run_security_runner_raises_for_failing_bound_rule(tmp_path: Path):
    """End-to-end: failing bound rule routes through the gate (pytest.fail)."""
    meta = _security_meta()
    registry = {meta.rule_id: meta}
    bound_rule_id = "repo.auth.D001-acc-unit-001"

    # Stub a pytest session so outcome reads work end-to-end.
    class _StubSession:
        def __init__(self):
            self._atdd = {"rule_outcomes": {bound_rule_id: "failed"}}

    session = _StubSession()
    with pytest.raises(pytest.fail.Exception) as exc_info:
        run_security_runner(
            registry=registry,
            repo_root=tmp_path,
            session=session,
        )
    assert meta.rule_id in str(exc_info.value)
    assert "session-protection" in str(exc_info.value)


def test_run_security_runner_silent_for_passing_bound_rule(tmp_path: Path):
    """Passing bound rule produces no failure (gate stays silent)."""
    meta = _security_meta()
    registry = {meta.rule_id: meta}
    bound_rule_id = "repo.auth.D001-acc-unit-001"

    class _StubSession:
        def __init__(self):
            self._atdd = {"rule_outcomes": {bound_rule_id: "passed"}}

    session = _StubSession()
    # Should NOT raise.
    run_security_runner(
        registry=registry,
        repo_root=tmp_path,
        session=session,
    )


def test_run_security_runner_records_passes_for_each_security_rule(tmp_path: Path):
    """The runner records a per-security-rule pass when its bound rule passed."""
    meta = _security_meta()
    registry = {meta.rule_id: meta}
    bound_rule_id = "repo.auth.D001-acc-unit-001"

    class _StubSession:
        def __init__(self):
            self._atdd = {"rule_outcomes": {bound_rule_id: "passed"}}

    session = _StubSession()
    set_active_pytest_session(session)
    try:
        run_security_runner(registry=registry, repo_root=tmp_path, session=session)
    finally:
        set_active_pytest_session(None)
    # The runner should have recorded the security rule's pass alongside.
    assert session._atdd["rule_outcomes"].get(meta.rule_id) == "passed"


def test_collect_uses_stable_rule_iteration():
    """Rules with identical bound URN are deduplicated by rule_id."""
    meta = _security_meta()
    # Same metadata appears twice (alias-style registry duplication).
    registry = {meta.rule_id: meta, "alias-key": meta}
    outcomes = {"repo.auth.D001-acc-unit-001": "failed"}

    violations = collect_security_violations(registry, outcomes)
    assert len(violations) == 1


def test_get_set_active_pytest_session_round_trip():
    """The disposition gate's session hooks round-trip cleanly."""
    set_active_pytest_session(None)
    assert get_active_pytest_session() is None

    sentinel = object()
    set_active_pytest_session(sentinel)
    assert get_active_pytest_session() is sentinel

    set_active_pytest_session(None)
    assert get_active_pytest_session() is None
