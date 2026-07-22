# URN: test:govern-registry:D001-UNIT-001-admitting-extensions-adds-no-rule-only-duplicates
# Acceptance: acc:govern-registry:D001-UNIT-001-admitting-extensions-adds-no-rule-only-duplicates
# WMBT: wmbt:govern-registry:D001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:D001-UNIT-001-admitting-extensions-adds-no-rule-only-duplicates.

When every extension rule_id mirrors a core rule_id (the designed state), admitting
the extension tree into the registry contributes ZERO new rule_ids and exactly one
duplicate per mirrored rule — the evidence that Path A gains nothing by reading
extensions.
"""
from __future__ import annotations

from atdd.enforce.registry import duplicate_rule_ids, new_rules_from_extensions


def test_admitting_extensions_adds_no_rule_only_duplicates() -> None:
    core_ids = {
        "coder.refactor.complexity-cognitive",
        "coder.dead-code.reachability",
        "coder.security.sql-injection",
    }
    # Every extension id mirrors a core id (a strict subset).
    extension_ids = {
        "coder.refactor.complexity-cognitive",
        "coder.dead-code.reachability",
    }

    # Admitting the extensions adds no NEW rule.
    assert new_rules_from_extensions(core_ids, extension_ids) == set()

    # Each mirror only duplicates its core twin — the collision set IS the ext set.
    assert duplicate_rule_ids(core_ids, extension_ids) == extension_ids
