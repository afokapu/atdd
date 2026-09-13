# URN: test:coach:urn:typed-train-journey
"""
Issue #1986 — a typed train JOURNEY test URN was ungrammatical.

The same defect #1548 fixed for ``acc:``, one family over. The ``test:`` pattern
documents its journey shape as ``test:train:{train_id}:{HARNESS}-{NNN}-{slug}``,
but the only ``train:`` alternative it implemented was the legacy four-digit
``train:\\d{4}-slug``. Once #1421 retyped a train to ``train:<subject>:<slug>``,
its journey URN stopped matching the very pattern whose comment promised it.

This was not theoretical: every train already retyped carried a broken journey
URN -- ``documentation-obligation`` (x4), ``coach:place-worktrees``,
``issue-lifecycle:record-agent-session-identity`` (x2) and
``self-compliance:validate-lifecycle`` -- eight in all, reported by
``atdd repo broken`` and unnoticed because the diagnostic already carried a
large backlog. Migrating the last seven legacy trains (#1986) would have added
seven more rather than exposing the cause.

The legacy alternative is deliberately KEPT: dual-resolution outlives the
migration window, so both spellings must validate until the fork is retired.
"""

from __future__ import annotations

import pytest

from atdd.coach.utils.graph.urn import URNGrammar


TYPED_JOURNEY = "test:train:extension-conventions:enforce-strict-failure:E2E-001-strict-violation-fails"
LEGACY_JOURNEY = "test:train:0201-enforce-strict-failure:E2E-001-strict-violation-fails"
WAGON_TEST = "test:author-atdd-substrate:author-issue-body:E025-UNIT-001-body-shape"

#: The typed journey URNs #1421 already created and left ungrammatical.
ALREADY_RETYPED = [
    "test:train:documentation-obligation:prove-documentation-obligation:E2E-001-declaration-smoke",
    "test:train:documentation-obligation:proceed-without-capability:E2E-001-declaration-smoke",
    "test:train:coach:place-worktrees:E2E-001-place-worktrees-journey",
    "test:train:issue-lifecycle:record-agent-session-identity:E2E-002-shipped-table-smoke",
    "test:train:self-compliance:validate-lifecycle:SMOKE-001-idempotent",
]


def test_typed_train_journey_is_regex_valid() -> None:
    assert URNGrammar.validate_urn(TYPED_JOURNEY, "test") is True


@pytest.mark.parametrize("urn", ALREADY_RETYPED)
def test_journey_urns_of_already_retyped_trains_are_valid(urn: str) -> None:
    """Regression: these were broken before #1986 widened the pattern."""
    assert URNGrammar.validate_urn(urn, "test") is True


def test_legacy_journey_still_valid_during_the_migration_window() -> None:
    """Dual-resolution outlives the migration; the legacy spelling must not break."""
    assert URNGrammar.validate_urn(LEGACY_JOURNEY, "test") is True


def test_wagon_scoped_test_urn_is_unaffected() -> None:
    assert URNGrammar.validate_urn(WAGON_TEST, "test") is True


# ---------------------------------------------------------------------------
# The widening is BOUNDED — near-misses must still be rejected
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "urn,why",
    [
        ("test:train:extension-conventions:enforce-strict-failure:NOPE-001-x",
         "NOPE is not a declared harness kind"),
        ("test:train:extension-conventions:enforce-strict-failure:E2E-1-x",
         "the ordinal must be three digits"),
        ("test:train:Extension-Conventions:enforce-strict-failure:E2E-001-x",
         "the subject must be kebab-case lowercase"),
    ],
)
def test_near_misses_are_still_rejected(urn: str, why: str) -> None:
    assert URNGrammar.validate_urn(urn, "test") is False, f"should reject: {why}"
