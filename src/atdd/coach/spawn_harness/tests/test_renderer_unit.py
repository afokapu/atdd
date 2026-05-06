# URN: component:govern-lifecycle:enforcement-substrate:spawn_harness:tests:test_renderer_unit
# Runtime: python
# Purpose: Per-block unit tests for the substrate spawn-harness renderer.

"""Per-block unit tests for the spawn-harness renderer (issue #417).

Covers the wmbt/train/security block emitters individually, plus the
phase-filter and train-scope-filter behavior the snapshot test does not
exercise in isolation.
"""
from __future__ import annotations

from pathlib import Path

from atdd.coach.spawn_harness import (
    render_security_rules_block,
    render_spawn_blocks,
    render_train_rules_block,
    render_wmbt_rules_block,
)
from atdd.coach.utils.rule_binding import RuleMetadata


def _wmbt_rule(rule_id: str, wmbt_urn: str, *, phase: str = "GREEN") -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        severity=4,
        description="purpose-line for " + rule_id,
        recipe=None,
        introduced_in=None,
        source_path=Path("/fixture/plan/wagon/D001.yaml"),
        disposition="strict",
        validator=None,
        fix_hint=None,
        aliases=(),
        acceptance_urn=f"acc:wagon:{rule_id}",
        wmbt_urn=wmbt_urn,
        phase=phase,
        then=("expectation a", "expectation b"),
    )


def _train_rule(rule_id: str, train_urn: str, *, phase: str = "SMOKE") -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        severity=4,
        description="train purpose for " + rule_id,
        recipe=None,
        introduced_in=None,
        source_path=Path("/fixture/plan/_trains/some-train.yaml"),
        disposition="strict",
        validator=None,
        fix_hint=None,
        aliases=(),
        acceptance_urn=f"acc:some-train:{rule_id}",
        train_urn=train_urn,
        phase=phase,
        then=("train expectation",),
    )


def _security_rule(rule_id: str, *, phase: str = "GREEN") -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        severity=3,
        description="Threat Name — threat description",
        recipe=None,
        introduced_in=None,
        source_path=Path("/fixture/plan/auth/feature.yaml"),
        disposition="strict",
        validator=None,
        fix_hint="mitigation prose",
        aliases=(),
        security_urn=f"security:auth:{rule_id}",
        feature_urn="feature:auth:session",
        bound_acceptance_urn="acc:auth:D001-SEC-001-bound",
        phase=phase,
    )


# ---------------------------------------------------------------------------
# Phase filtering
# ---------------------------------------------------------------------------
def test_wmbt_rules_filters_by_phase():
    """Only WMBT rules whose ``phase`` matches ``coach_phase`` render."""
    rules = [
        _wmbt_rule("repo.w.D001-acc-unit-001", "wmbt:w:D001", phase="GREEN"),
        _wmbt_rule("repo.w.D002-acc-unit-001", "wmbt:w:D002", phase="RED"),
    ]
    out = render_wmbt_rules_block(rules, coach_phase="GREEN")
    assert "repo.w.D001-acc-unit-001" in out
    assert "repo.w.D002-acc-unit-001" not in out


def test_train_rules_filters_by_phase():
    """Only train rules whose ``phase`` matches ``coach_phase`` render."""
    rules = [
        _train_rule("repo.t.acc-a", "train:t", phase="SMOKE"),
        _train_rule("repo.t.acc-b", "train:t", phase="GREEN"),
    ]
    out = render_train_rules_block(
        rules, coach_phase="SMOKE", train_scope=("train:t",)
    )
    assert "repo.t.acc-a" in out
    assert "repo.t.acc-b" not in out


def test_train_rules_filters_by_train_scope():
    """Train rules outside the supplied ``train_scope`` set are dropped."""
    rules = [
        _train_rule("repo.a.acc-a", "train:a", phase="SMOKE"),
        _train_rule("repo.b.acc-b", "train:b", phase="SMOKE"),
    ]
    out = render_train_rules_block(
        rules, coach_phase="SMOKE", train_scope=("train:a",)
    )
    assert "train:a" in out
    assert "train:b" not in out
    assert "repo.b.acc-b" not in out


def test_train_rules_empty_scope_renders_no_block():
    """When the scope set is empty, the train_rules block is omitted."""
    rules = [_train_rule("repo.t.acc-a", "train:t", phase="SMOKE")]
    out = render_train_rules_block(rules, coach_phase="SMOKE", train_scope=())
    assert out == ""


# ---------------------------------------------------------------------------
# Field-name pinning (short names per spec §8.2)
# ---------------------------------------------------------------------------
def test_wmbt_block_uses_short_field_names():
    """Output uses ``purpose``/``expectations`` not ``description``/``then``."""
    rules = [_wmbt_rule("repo.w.D001-acc-unit-001", "wmbt:w:D001")]
    out = render_wmbt_rules_block(rules, coach_phase="GREEN")
    assert "purpose:" in out
    assert "expectations:" in out
    assert "description:" not in out
    # 'then:' is not used for expectations rendering.
    assert "\n        then:" not in out


def test_security_block_maps_bound_acceptance_to_acceptance_ref():
    """``bound_acceptance_urn`` renders as ``acceptance_ref`` (spec §8.2)."""
    rules = [_security_rule("repo.auth.session-management-security-001")]
    out = render_security_rules_block(rules, coach_phase="GREEN")
    assert "acceptance_ref: acc:auth:D001-SEC-001-bound" in out
    assert "bound_acceptance_urn" not in out


def test_security_block_emits_threat_mitigation_severity():
    """Security rule rendering pins the spec-mandated short field names."""
    rules = [_security_rule("repo.auth.session-management-security-001")]
    out = render_security_rules_block(rules, coach_phase="GREEN")
    assert "threat:" in out
    assert "mitigation:" in out
    assert "severity: 3" in out


# ---------------------------------------------------------------------------
# Empty-block elision
# ---------------------------------------------------------------------------
def test_render_spawn_blocks_omits_empty_blocks():
    """When no rules of a kind survive filtering, the block is omitted."""
    rules = [_wmbt_rule("repo.w.D001-acc-unit-001", "wmbt:w:D001", phase="GREEN")]
    out = render_spawn_blocks(rules, coach_phase="GREEN", train_scope=())
    assert "wmbt_rules:" in out
    assert "train_rules:" not in out
    assert "security_rules:" not in out


def test_render_spawn_blocks_returns_empty_when_no_repo_rules():
    """All three blocks omitted when the registry has no repo rules."""
    out = render_spawn_blocks([], coach_phase="GREEN", train_scope=())
    assert out == ""


# ---------------------------------------------------------------------------
# Expectations source — list, not joined string
# ---------------------------------------------------------------------------
def test_expectations_use_then_list_not_joined_string():
    """Each ``then`` list element appears as its own bullet under expectations."""
    rule = _wmbt_rule("repo.w.D001-acc-unit-001", "wmbt:w:D001")
    out = render_wmbt_rules_block([rule], coach_phase="GREEN")
    # Two expectation lines, each on its own line.
    assert "- expectation a" in out
    assert "- expectation b" in out
    # The joined-string form must NOT appear.
    assert "expectation a; expectation b" not in out
