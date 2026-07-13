# URN: test:govern-projection-fields:define-field-ownership:C001-UNIT-001-red-omitted-field-accepted
# Acceptance: acc:govern-projection-fields:C001-UNIT-001-red-omitted-field-accepted
# WMBT: wmbt:govern-projection-fields:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: a field-ownership policy that omits a projection schema field loads without complaint — and the coverage check refuses it, naming the uncovered field `body` and exiting non-zero, because an unowned field is one every writer may write and no merge rule governs. Refs #1400.
"""An omitted field is an unowned field, and the coverage check refuses it (C001-UNIT-001).

wagon: govern-projection-fields | feature: define-field-ownership | phase: RED
WMBT: wmbt:govern-projection-fields:C001

A policy with a hole in it is worse than an obviously broken one, because it *works*. It
parses, it loads, and every field it does declare is enforced — so nothing anywhere says
that ``body`` fell out of the table. What it silently means is that ``body`` has no writer
(so no wrong-writer check can fire on it) and no merge rule (so the driver has nothing to
merge it by). The gap is only ever visible at the moment somebody corrupts the field.

So authoring is where it has to be caught: the coverage check refuses a policy that leaves
any projection schema field unowned, and names the field.
"""
from __future__ import annotations

from atdd.state import ownership
from atdd.state.cli import run

from ._helpers import policy_document, write_policy


def test_c001_unit_001_red_omitted_field_accepted(tmp_path) -> None:
    """The loader accepts the gap; the coverage check names it and exits non-zero."""
    gapped = policy_document(omit="body")

    # The loader is happy: nothing about parsing a policy notices a missing entry.
    policy = ownership.FieldOwnershipPolicy.from_document(gapped)
    assert "body" not in policy
    assert "phase" in policy, "the omission is surgical; the rest of the table is intact"

    # And that is exactly the danger: with no entry, `body` resolves to no writer at all.
    report = ownership.check_coverage(gapped)

    assert not report.ok
    assert report.uncovered == ["body"]
    assert "body" in report.render()
    assert "uncovered" in report.render()

    # The check *exits non-zero* rather than accepting the policy — the property CI leans on.
    write_policy(tmp_path, gapped)
    assert run(["ownership-check", "--root", str(tmp_path)]) == 1

    # The same check over a policy with no hole exits zero, so the refusal is about the gap
    # and not about the checker refusing everything.
    write_policy(tmp_path, policy_document())
    assert run(["ownership-check", "--root", str(tmp_path)]) == 0
