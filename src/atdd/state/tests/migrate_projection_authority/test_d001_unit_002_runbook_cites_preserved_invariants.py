# URN: test:migrate-projection-authority:describe-migration-runbook:D001-UNIT-002-runbook-cites-preserved-invariants
# Acceptance: acc:migrate-projection-authority:D001-UNIT-002-runbook-cites-preserved-invariants
# WMBT: wmbt:migrate-projection-authority:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Every runbook section cites at least one NUMBERED invariant, and no section cites an invariant that does not exist — where "exists" means the spec's own §2.2 table, parsed out of the spec rather than copied into the checker. Refs #1434.
"""Every step names the invariant it preserves, and the invariant is real (D001-UNIT-002).

wagon: migrate-projection-authority | feature: describe-migration-runbook | phase: GREEN
WMBT: wmbt:migrate-projection-authority:D001

"Run the migration tool" is an instruction. "Run the migration tool; it preserves I1, so a second
run reproduces the first byte for byte" is an instruction the reader can *verify they followed
correctly* — which is the only kind worth writing for a one-way door. A step that cannot name what
it preserves is a step whose author did not know.

The second half matters as much: the citation must be to an invariant that **exists**. The legal
set is parsed out of the architecture spec's §2.2 table, not hardcoded in the checker — a copy
there would let the runbook and the architecture drift apart while the checker cheerfully agreed
with both. Refs #1434 / #1400.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.runbook import (
    MIGRATION_STEPS,
    RULE_NO_INVARIANT,
    RULE_UNKNOWN_INVARIANT,
    check,
    spec_invariants,
)

REPO = Path(__file__).resolve().parents[5]
_RUNBOOK = REPO / "docs" / "atdd-migration-runbook.md"


def test_d001_unit_002_runbook_cites_preserved_invariants(tmp_path) -> None:
    """Every section cites a real numbered invariant; a citation of a non-existent one fails."""
    report = check(REPO)
    assert report.ok, report.render()

    # The legal set comes from the SPEC, parsed — I1..I8 of §2.2.
    known = spec_invariants(REPO / "docs" / "atdd-state-projection-plan.md")
    assert known == [f"I{n}" for n in range(1, 9)], known
    assert report.known_invariants == known

    # Every step cites at least one, and every citation is in the legal set.
    for step in MIGRATION_STEPS:
        cited = report.citations[step.slug]
        assert cited, f"`{step.slug}` cites no numbered invariant"
        assert set(cited) <= set(known), f"`{step.slug}` cites something the spec does not declare"

    # The check BITES, both ways.

    # (a) a section citing an invariant that does not exist. I9 is not in the spec, and the check
    #     must know that because it READ the spec — not because it was told.
    forged = tmp_path / "forged.md"
    text = _RUNBOOK.read_text(encoding="utf-8")
    forged.write_text(text.replace("**Invariant**: **I1**", "**Invariant**: **I9**", 1),
                      encoding="utf-8")
    unknown = check(REPO, runbook=forged)
    assert not unknown.ok
    problems = [p for p in unknown.problems if p.rule == RULE_UNKNOWN_INVARIANT]
    assert problems and "I9" in problems[0].detail

    # (b) a section citing none at all.
    silent = tmp_path / "silent.md"
    silent.write_text(
        text.replace("- **Invariant**: **I1** — `project(store)` is byte-identical", "- Invariant: none", 1),
        encoding="utf-8",
    )
    assert any(p.rule in (RULE_NO_INVARIANT,) for p in check(REPO, runbook=silent).problems)
