# URN: test:migrate-projection-authority:describe-migration-runbook:D001-UNIT-001-runbook-covers-every-migration-step
# Acceptance: acc:migrate-projection-authority:D001-UNIT-001-runbook-covers-every-migration-step
# WMBT: wmbt:migrate-projection-authority:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The authored core migration runbook has a named section for EVERY migration step this wagon ships, and each section states its command, its precondition, and its preserved invariant — a step the code ships but the doc omits fails the check, and so does a documented step the code does not ship. Refs #1434.
"""The runbook covers every step the code actually ships (D001-UNIT-001).

wagon: migrate-projection-authority | feature: describe-migration-runbook | phase: RED
WMBT: wmbt:migrate-projection-authority:D001

A runbook is the one migration artifact that rots silently: the code moves, the steps change, and
the document keeps confidently describing a cutover nobody performs — right up until the night
someone follows it. So it is checked against :data:`MIGRATION_STEPS`, in **both** directions. A
step the code ships and the doc omits is a gap someone will fall through. A step the doc describes
and the code does not ship is a lie with a heading. Refs #1434 / #1400.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.runbook import (
    MIGRATION_STEPS,
    REQUIRED_KEYS,
    RULE_MISSING_KEY,
    RULE_MISSING_SECTION,
    RULE_UNDOCUMENTED_SECTION,
    MigrationStep,
    check,
)

#: The real repo — the runbook under test is the one this wagon actually ships.
REPO = Path(__file__).resolve().parents[5]


def test_d001_unit_001_runbook_covers_every_migration_step(tmp_path) -> None:
    """Every shipped step has a section stating its command, precondition and invariant."""
    report = check(REPO)

    assert report.ok, report.render()

    # Every step the code ships is documented...
    documented = set(report.sections)
    for step in MIGRATION_STEPS:
        assert step.slug in documented, f"the runbook does not document `{step.slug}`"

    # ...and each section states all three required keys. (Proven by the check passing, but named
    # here so a reader of this test knows what "covers" means.)
    assert REQUIRED_KEYS == ("Command", "Precondition", "Invariant")

    # The check BITES — in both directions, or it is decoration.

    # (a) a step the code ships that the runbook omits.
    invented = (*MIGRATION_STEPS, MigrationStep("teleport", "a step nobody wrote down"))
    missing = check(REPO, steps=invented)
    assert not missing.ok
    assert any(p.rule == RULE_MISSING_SECTION and p.step == "teleport" for p in missing.problems)

    # (b) a section whose step the code does not ship.
    extra = check(REPO, steps=MIGRATION_STEPS[:-1])
    assert not extra.ok
    assert any(p.rule == RULE_UNDOCUMENTED_SECTION for p in extra.problems)

    # (c) a section that omits one of the three required keys.
    stripped = tmp_path / "runbook.md"
    text = (REPO / "docs" / "atdd-migration-runbook.md").read_text(encoding="utf-8")
    stripped.write_text(text.replace("- **Precondition**", "- Precondition", 1), encoding="utf-8")
    keyless = check(REPO, runbook=stripped)
    assert not keyless.ok
    assert any(p.rule == RULE_MISSING_KEY for p in keyless.problems)
