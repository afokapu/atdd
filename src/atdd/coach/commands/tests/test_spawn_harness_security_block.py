# URN: urn:atdd:test:coach:commands:spawn_harness:security_block
# Issue: #422

"""Unit tests for ``render_security_rules_block`` (spec v12 §8.2).

The renderer's output must match the spec example structure:

    security_rules:
      - feature_urn: feature:auth:session-management
        rules:
          - id: repo.auth.session-management-security-001
            security_urn: security:auth:session-management:001
            threat: "Session Hijacking — Attacker steals session token via XSS"
            mitigation: "HttpOnly cookies, CSP headers"
            severity: 4
            acceptance_ref: acc:auth:D001-SEC-001-session-protection
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.spawn_harness_blocks import render_security_rules_block
from atdd.coach.utils.rule_binding import RuleMetadata


def _security_meta(
    *,
    rule_id: str = "repo.auth.session-management-security-001",
    feature_urn: str = "feature:auth:session-management",
    security_urn: str = "security:auth:session-management:001",
    bound_acc: str = "acc:auth:D001-SEC-001-session-protection",
    severity: int = 4,
    phase: str = "GREEN",
    description: str = "Session Hijacking — Attacker steals session token via XSS",
    fix_hint: str = "HttpOnly cookies, CSP headers",
) -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        severity=severity,
        description=description,
        recipe=None,
        introduced_in=None,
        source_path=Path("/tmp/feature.yaml"),
        disposition="strict",
        fix_hint=fix_hint,
        security_urn=security_urn,
        feature_urn=feature_urn,
        bound_acceptance_urn=bound_acc,
        phase=phase,
    )


def test_renders_block_matching_spec_example():
    """Output structure matches §8.2 spawn-harness security_rules example."""
    meta = _security_meta()

    blocks = render_security_rules_block([meta])
    assert blocks == [
        {
            "feature_urn": "feature:auth:session-management",
            "rules": [
                {
                    "id": "repo.auth.session-management-security-001",
                    "security_urn": "security:auth:session-management:001",
                    "threat": (
                        "Session Hijacking — Attacker steals session token via XSS"
                    ),
                    "mitigation": "HttpOnly cookies, CSP headers",
                    "severity": 4,
                    "acceptance_ref": (
                        "acc:auth:D001-SEC-001-session-protection"
                    ),
                },
            ],
        }
    ]


def test_skips_rules_missing_required_fields():
    """Rules without security_urn / feature_urn / bound_acc are excluded."""
    meta = _security_meta(security_urn=None)  # type: ignore[arg-type]

    blocks = render_security_rules_block([meta])
    assert blocks == []


def test_groups_rules_by_feature_urn():
    """Two rules under the same feature share one block; deterministic order."""
    a = _security_meta(
        rule_id="repo.auth.feature-a-security-001",
        feature_urn="feature:auth:feature-a",
        security_urn="security:auth:feature-a:001",
    )
    b = _security_meta(
        rule_id="repo.auth.feature-a-security-002",
        feature_urn="feature:auth:feature-a",
        security_urn="security:auth:feature-a:002",
    )
    z = _security_meta(
        rule_id="repo.auth.zfeature-security-001",
        feature_urn="feature:auth:zfeature",
        security_urn="security:auth:zfeature:001",
    )

    blocks = render_security_rules_block([z, b, a])
    assert [b["feature_urn"] for b in blocks] == [
        "feature:auth:feature-a",
        "feature:auth:zfeature",
    ]
    feature_a_block = blocks[0]
    assert [r["id"] for r in feature_a_block["rules"]] == [
        "repo.auth.feature-a-security-001",
        "repo.auth.feature-a-security-002",
    ]


def test_phase_filter_includes_only_matching_phase():
    """``coach_phase=GREEN`` excludes rules whose phase != GREEN."""
    green = _security_meta(
        rule_id="repo.auth.feature-a-security-001",
        feature_urn="feature:auth:feature-a",
        security_urn="security:auth:feature-a:001",
        phase="GREEN",
    )
    smoke = _security_meta(
        rule_id="repo.auth.feature-b-security-001",
        feature_urn="feature:auth:feature-b",
        security_urn="security:auth:feature-b:001",
        phase="SMOKE",
    )

    blocks = render_security_rules_block([green, smoke], coach_phase="GREEN")
    feature_urns = [b["feature_urn"] for b in blocks]
    assert feature_urns == ["feature:auth:feature-a"]


def test_no_phase_filter_includes_everything():
    """``coach_phase=None`` (default) includes every well-formed security rule."""
    green = _security_meta(
        rule_id="repo.auth.a-security-001",
        feature_urn="feature:auth:a",
        security_urn="security:auth:a:001",
        phase="GREEN",
    )
    smoke = _security_meta(
        rule_id="repo.auth.b-security-001",
        feature_urn="feature:auth:b",
        security_urn="security:auth:b:001",
        phase="SMOKE",
    )

    blocks = render_security_rules_block([green, smoke])
    feature_urns = [b["feature_urn"] for b in blocks]
    assert feature_urns == ["feature:auth:a", "feature:auth:b"]
