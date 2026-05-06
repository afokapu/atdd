# URN: urn:atdd:test:runners:security_runner:validation
# Issue: #422

"""Validation-time integration tests for the security enforcement rule.

Spec v12 §7.4 — ``test_every_abuse_case_resolves`` runs at validation
time (NOT runtime) and surfaces broken acceptance_refs via the
``security-rule-must-have-acceptance-ref-resolved`` enforcement rule.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from atdd.coach.utils.disposition_gate import set_active_pytest_session
from atdd.coach.utils.rule_binding import clear_cache


@pytest.fixture(autouse=True)
def _reset_cache():
    set_active_pytest_session(None)
    clear_cache()
    yield
    set_active_pytest_session(None)
    clear_cache()


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip(), encoding="utf-8")
    return path


def _author_repo_with_broken_acceptance_ref(tmp_path: Path) -> Path:
    """Author a repo with one feature.yaml whose acceptance_ref is broken."""
    (tmp_path / "plan").mkdir()
    _write(
        tmp_path / "plan" / "auth" / "features" / "session_management.yaml",
        """
        urn: "feature:auth:session-management"
        security:
          abuse_cases:
            - id: "THREAT-001"
              name: "Session Hijacking"
              threat: "Attacker steals session token via XSS"
              mitigation: "HttpOnly cookies, CSP headers"
              severity: high
              acceptance_ref: "acc:auth:D001-UNIT-001-session-protection"
        """,
    )
    # No bound WMBT — acceptance_ref does not resolve.
    return tmp_path


def test_validation_rule_fires_for_broken_acceptance_ref(tmp_path: Path, monkeypatch):
    """The validation-time rule emits one violation for an unresolved acceptance_ref.

    Spec v12 §7.4 — surfaces at ``atdd repo validate`` time, before any
    pytest run.
    """
    repo_root = _author_repo_with_broken_acceptance_ref(tmp_path)
    # Point the runner at the fixture repo.
    monkeypatch.chdir(repo_root)
    clear_cache(override_repo_root=repo_root)
    monkeypatch.setattr(
        "atdd.tester.validators.test_security_ref_binding.find_repo_root",
        lambda: repo_root,
    )

    from atdd.tester.validators.test_security_ref_binding import test_every_abuse_case_resolves

    with pytest.raises(pytest.fail.Exception) as exc_info:
        test_every_abuse_case_resolves()

    msg = str(exc_info.value)
    assert (
        "tester.acceptance-violation.security-rule-must-have-acceptance-ref-resolved"
        in msg
    )
    assert "THREAT-001" in msg
    assert "acc:auth:D001-UNIT-001-session-protection" in msg


def test_validation_rule_silent_when_all_acceptance_refs_resolve(
    tmp_path: Path, monkeypatch
):
    """No violations → the validation-time rule passes silently."""
    repo_root = tmp_path
    (repo_root / "plan").mkdir()

    # Author a feature with a resolvable acceptance_ref + the bound WMBT.
    _write(
        repo_root / "plan" / "auth" / "features" / "session_management.yaml",
        """
        urn: "feature:auth:session-management"
        security:
          abuse_cases:
            - id: "THREAT-001"
              name: "Session Hijacking"
              threat: "Attacker steals session token via XSS"
              mitigation: "HttpOnly cookies, CSP headers"
              severity: high
              acceptance_ref: "acc:auth:D001-UNIT-001-session-protection"
        """,
    )
    _write(
        repo_root / "plan" / "auth" / "D001.yaml",
        """
        urn: "wmbt:auth:D001"
        step: define
        direction: minimize
        dimension: quantity
        object_of_control: stolen-session-tokens
        context_clarifier: ctx
        lens: functional.security
        statement: "minimize stolen session tokens"
        acceptances:
          - identity:
              urn: "acc:auth:D001-UNIT-001-session-protection"
              purpose: "Session tokens are not exfiltrable via XSS"
              phase: "GREEN"
            harness:
              type: unit
            given:
              abstract: ["session cookie has HttpOnly flag"]
            when:
              abstract: "an injected script reads document.cookie"
            then:
              abstract: ["the cookie value is unavailable to scripts"]
        """,
    )

    monkeypatch.chdir(repo_root)
    clear_cache(override_repo_root=repo_root)
    monkeypatch.setattr(
        "atdd.tester.validators.test_security_ref_binding.find_repo_root",
        lambda: repo_root,
    )

    from atdd.tester.validators.test_security_ref_binding import test_every_abuse_case_resolves

    # Should NOT raise.
    test_every_abuse_case_resolves()


def test_disposition_gate_records_failed_outcome_to_active_session():
    """Spec §4.5 — the gate writes rule_id outcomes to session._atdd['rule_outcomes']."""
    from atdd.coach.utils.disposition_gate import (
        assert_disposition_satisfied,
        set_active_pytest_session,
    )
    from atdd.coach.utils.rule_id_registry import RuleMetadata
    from atdd.coach.validators._violation import Violation

    class _StubSession:
        def __init__(self):
            self._atdd: dict = {}

    session = _StubSession()
    set_active_pytest_session(session)
    try:
        registry = {
            "fixture.rule.one": RuleMetadata(
                rule_id="fixture.rule.one",
                convention_path=Path("/tmp/fixture.yaml"),
                severity=4,
                description="fixture",
                disposition="strict",
            ),
        }
        v = Violation(
            rule_id="fixture.rule.one",
            severity=4,
            location="fixture.py:1",
            detail="fixture violation",
        )
        with pytest.raises(pytest.fail.Exception):
            assert_disposition_satisfied(
                validator_id="test_fixture::test_x",
                violations=[v],
                registry=registry,
            )
    finally:
        set_active_pytest_session(None)

    assert session._atdd["rule_outcomes"]["fixture.rule.one"] == "failed"


def test_record_rule_outcome_promotes_failure_over_pass():
    """Last-write-wins for failures: a failure recorded after a pass stays failed."""
    from atdd.coach.utils.disposition_gate import (
        record_rule_outcome,
        set_active_pytest_session,
    )

    class _StubSession:
        def __init__(self):
            self._atdd: dict = {}

    session = _StubSession()
    set_active_pytest_session(session)
    try:
        record_rule_outcome("fixture.rule.x", "passed")
        record_rule_outcome("fixture.rule.x", "failed")
        assert session._atdd["rule_outcomes"]["fixture.rule.x"] == "failed"

        record_rule_outcome("fixture.rule.x", "passed")
        # Second pass MUST NOT downgrade the failure.
        assert session._atdd["rule_outcomes"]["fixture.rule.x"] == "failed"
    finally:
        set_active_pytest_session(None)


def test_record_rule_outcome_no_op_outside_pytest():
    """Outside an active pytest session the writes are silent no-ops."""
    from atdd.coach.utils.disposition_gate import (
        record_rule_outcome,
        set_active_pytest_session,
    )

    set_active_pytest_session(None)
    # Should not raise.
    record_rule_outcome("any.rule.id", "passed")
    record_rule_outcome("any.rule.id", "failed")
