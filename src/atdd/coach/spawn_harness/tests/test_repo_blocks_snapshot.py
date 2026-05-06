# URN: component:govern-lifecycle:enforcement-substrate:spawn_harness:tests:test_repo_blocks_snapshot
# Runtime: python
# Purpose: Snapshot test for substrate spec v12 §8.2 spawn-harness output.

"""Snapshot test for the spawn-harness repo-rule blocks (issue #417 AC).

Builds a fixture registry containing one WMBT rule, one train rule, and
one security rule, runs ``render_spawn_blocks(rules, coach_phase=...)``,
and diffs the YAML output against
``fixtures/expected_spawn_blocks.yaml``. The expected output is
byte-identical to spec §8.2 lines 600–633 modulo URN substitution.

Per the issue, the renderer must:

* Emit the SHORT field names from the spec example (``acceptance_ref``,
  ``purpose``, ``expectations``, ``threat``, ``mitigation``,
  ``severity``) NOT the RuleMetadata internal names
  (``bound_acceptance_urn``, ``description``, ``then`` list).
* Map ``RuleMetadata.bound_acceptance_urn`` → output ``acceptance_ref``
  for security rules.
* Source ``expectations:`` from the FULL ``RuleMetadata.then`` list
  (not the joined ``fix_hint`` string).
"""
from __future__ import annotations

from pathlib import Path

from atdd.coach.spawn_harness import render_spawn_blocks
from atdd.coach.utils.rule_binding import RuleMetadata


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _build_fixture_rules() -> list[RuleMetadata]:
    """Return three rules (one WMBT, one train, one security) at GREEN phase."""
    wmbt_rule = RuleMetadata(
        rule_id="repo.govern-lifecycle.D010-acc-unit-001",
        severity=4,
        description=(
            "A single get_theme_map(config) helper replaces every "
            "hardcoded theme_map dict in the codebase"
        ),
        recipe=None,
        introduced_in=None,
        source_path=Path("/fixture/plan/govern-lifecycle/D010.yaml"),
        disposition="strict",
        validator=None,
        fix_hint=None,
        aliases=(),
        acceptance_urn=(
            "acc:govern-lifecycle:"
            "D010-UNIT-001-single-source-theme-map-helper"
        ),
        wmbt_urn="wmbt:govern-lifecycle:D010",
        phase="GREEN",
        then=(
            "No theme_map dict literal appears outside coach/utils/theme_map.py",
            "inventory.py, registry.py, and test_train_validation.py "
            "import and call get_theme_map",
            "The helper is the single source of truth for the "
            "digit-to-theme mapping",
        ),
    )

    train_rule = RuleMetadata(
        rule_id="repo.checkout-train.acc-idempotent-on-retry",
        severity=4,
        description=(
            "Re-running the flow with the same idempotency key produces "
            "no duplicate side effects"
        ),
        recipe=None,
        introduced_in=None,
        source_path=Path("/fixture/plan/_trains/checkout-train.yaml"),
        disposition="strict",
        validator=None,
        fix_hint=None,
        aliases=(),
        acceptance_urn="acc:checkout-train:idempotent-on-retry",
        train_urn="train:checkout-train",
        phase="GREEN",
        then=(
            "Repeating a charge with the same key returns the original receipt",
            "No second downstream webhook is emitted",
        ),
    )

    security_rule = RuleMetadata(
        rule_id="repo.auth.session-management-security-001",
        severity=4,
        description="Session Hijacking — Attacker steals session token via XSS",
        recipe=None,
        introduced_in=None,
        source_path=Path("/fixture/plan/auth/session-management.feature.yaml"),
        disposition="strict",
        validator=None,
        fix_hint="HttpOnly cookies, CSP headers",
        aliases=(),
        security_urn="security:auth:session-management:001",
        feature_urn="feature:auth:session-management",
        bound_acceptance_urn="acc:auth:D001-SEC-001-session-protection",
        phase="GREEN",
    )

    return [wmbt_rule, train_rule, security_rule]


def test_render_spawn_blocks_matches_expected_snapshot():
    """``render_spawn_blocks`` produces YAML byte-identical to the fixture."""
    rules = _build_fixture_rules()

    rendered = render_spawn_blocks(
        rules,
        coach_phase="GREEN",
        train_scope=("train:checkout-train",),
    )

    expected = (_FIXTURE_DIR / "expected_spawn_blocks.yaml").read_text()

    assert rendered == expected, (
        "spawn-harness output diverged from spec §8.2 fixture. "
        "If the spec changed, regenerate fixtures/expected_spawn_blocks.yaml.\n"
        f"--- expected ---\n{expected}\n--- got ---\n{rendered}\n"
    )
