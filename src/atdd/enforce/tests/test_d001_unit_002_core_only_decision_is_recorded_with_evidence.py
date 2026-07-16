# URN: test:govern-registry:D001-UNIT-002-core-only-decision-is-recorded-with-evidence
# Acceptance: acc:govern-registry:D001-UNIT-002-core-only-decision-is-recorded-with-evidence
# WMBT: wmbt:govern-registry:D001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:D001-UNIT-002-core-only-decision-is-recorded-with-evidence.

The Path-A-stays-core-only decision is written down with its rationale and
evidence, not left to assumption — a durable, auditable decision record.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root


def test_core_only_decision_is_recorded_with_evidence() -> None:
    doc = find_repo_root() / "docs" / "registry-scope-decision.md"
    assert doc.is_file(), f"decision record missing at {doc}"
    text = doc.read_text(encoding="utf-8").lower()

    # Records the decision itself.
    assert "core-only" in text
    assert "atdd validate" in text

    # Names the evidence behind it.
    assert "find_convention_files" in text
    assert "src/atdd" in text
    assert ".atdd/extensions" in text
    assert "373" in text  # core rule count
    assert "50" in text   # extension rule count
    assert "mirror" in text  # every extension node mirrors a live core rule
