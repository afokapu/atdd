# URN: urn:atdd:test:coach:commands:rules:security_rules_cli
# Issue: #422

"""Unit tests for ``atdd repo security-rules <feature-urn>`` (spec v12 §9.1)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from atdd.coach.utils.rule_binding import clear_cache


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def test_rejects_non_feature_urn(capsys):
    """Subcommand validates the URN family before walking the registry."""
    from atdd.coach.commands.rules import RepoRulesListing

    rc = RepoRulesListing().list_rules_for_feature(
        "wmbt:auth:D001", format="text"
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "expected feature URN" in captured.err


def test_lists_security_rules_for_feature(monkeypatch, tmp_path: Path, capsys):
    """``security-rules`` renders the matching rules for the given feature URN."""
    from atdd.coach.commands.rules import RepoRulesListing
    from atdd.coach.utils.rule_binding import RuleMetadata

    fake_meta = RuleMetadata(
        rule_id="repo.auth.session-management-security-001",
        severity=4,
        description="Session Hijacking — Attacker steals session token via XSS",
        recipe=None,
        introduced_in=None,
        source_path=Path("/tmp/feature.yaml"),
        disposition="strict",
        validator=(
            "test_security_ref_binding::test_acceptance_ref_resolves_and_passes"
        ),
        fix_hint="HttpOnly cookies, CSP headers",
        security_urn="security:auth:session-management:001",
        feature_urn="feature:auth:session-management",
        bound_acceptance_urn="acc:auth:D001-UNIT-001-session-protection",
    )

    def _stub_iter():
        yield fake_meta

    monkeypatch.setattr("atdd.coach.commands.rules.iter_rules", _stub_iter)

    rc = RepoRulesListing().list_rules_for_feature(
        "feature:auth:session-management", format="text"
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "feature:auth:session-management" in out
    assert "repo.auth.session-management-security-001" in out
    assert "security:auth:session-management:001" in out
    assert "acc:auth:D001-UNIT-001-session-protection" in out


def test_lists_security_rules_json(monkeypatch, capsys):
    """JSON output preserves all substrate discriminator fields."""
    from atdd.coach.commands.rules import RepoRulesListing
    from atdd.coach.utils.rule_binding import RuleMetadata

    fake_meta = RuleMetadata(
        rule_id="repo.auth.session-management-security-001",
        severity=4,
        description="Session Hijacking — Attacker steals session token via XSS",
        recipe=None,
        introduced_in=None,
        source_path=Path("/tmp/feature.yaml"),
        disposition="strict",
        validator=(
            "test_security_ref_binding::test_acceptance_ref_resolves_and_passes"
        ),
        fix_hint="HttpOnly cookies, CSP headers",
        security_urn="security:auth:session-management:001",
        feature_urn="feature:auth:session-management",
        bound_acceptance_urn="acc:auth:D001-UNIT-001-session-protection",
    )

    monkeypatch.setattr(
        "atdd.coach.commands.rules.iter_rules", lambda: iter([fake_meta])
    )

    rc = RepoRulesListing().list_rules_for_feature(
        "feature:auth:session-management", format="json"
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 1
    record = payload[0]
    assert record["rule_id"] == "repo.auth.session-management-security-001"
    assert record["security_urn"] == "security:auth:session-management:001"
    assert record["bound_acceptance_urn"] == (
        "acc:auth:D001-UNIT-001-session-protection"
    )
    assert record["feature_urn"] == "feature:auth:session-management"


def test_returns_nonzero_when_no_matching_feature(monkeypatch, capsys):
    """Empty match → non-zero exit + 'No repo security rules' message."""
    from atdd.coach.commands.rules import RepoRulesListing

    monkeypatch.setattr("atdd.coach.commands.rules.iter_rules", lambda: iter([]))

    rc = RepoRulesListing().list_rules_for_feature(
        "feature:nonexistent:thing", format="text"
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert "No repo security rules" in out
