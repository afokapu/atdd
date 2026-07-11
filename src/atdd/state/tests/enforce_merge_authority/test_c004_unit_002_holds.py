# URN: test:enforce-merge-authority:enforce-rule-disposition:C004-UNIT-002-holds
# Acceptance: acc:enforce-merge-authority:C004-UNIT-002-holds
# WMBT: wmbt:enforce-merge-authority:C004
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: a convention node authored by train train:object-conflict-resolution:project-state is admitted when it ships disposition strict, or when it ships advisory WITH a written precondition and a named issue that discharges it; the scan is scoped to this train's nodes and leaves every other convention alone. Refs #1400.
"""Strict, or a paid-for advisory — nothing else (C004-UNIT-002).

wagon: enforce-merge-authority | feature: enforce-rule-disposition | phase: RED
WMBT: wmbt:enforce-merge-authority:C004

The rule is not "advisory is banned". It is "advisory must be *paid for*": a written
precondition saying what has to become true before it can go strict, and a named issue
that is on the hook for making it true. That is the difference between a deliberate,
dated compromise and a rule that quietly does nothing.

The scan is also *scoped*. It governs the nodes this train authored — declared by
``authored_by_train`` — and says nothing about anyone else's conventions, because a gate
that reaches beyond what its author is responsible for gets switched off. Refs #1400.
"""
from __future__ import annotations

import yaml

from atdd.state import dispositions
from atdd.state.dispositions import TRAIN_ID, check_node, scan_conventions

CONVENTION = {
    "schema_version": "1.0.0",
    "convention_id": "coder.projection",
    "name": "Projection Convention",
    "authored_by_train": TRAIN_ID,
    "rules": [
        {
            "id": "coder.projection.canonical-bytes",
            "disposition": "strict",
        },
        {
            "id": "coder.projection.no-host-paths",
            "disposition": "advisory",
            dispositions.PRECONDITION_KEY:
                "the manifest mirror still carries absolute paths in three bodies",
            dispositions.DISCHARGED_BY_KEY: "#1400 migrate-projection-authority",
        },
    ],
}

#: Somebody else's convention, in the same tree. It is advisory and unpaid — and it is
#: none of this train's business.
FOREIGN = {
    "schema_version": "1.0.0",
    "convention_id": "coach.legacy",
    "rules": [{"id": "coach.legacy.whatever", "disposition": "advisory"}],
}


def _write(root, package: str, name: str, document) -> None:
    path = root / "src" / "atdd" / package / "conventions" / f"{name}.convention.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def test_c004_unit_002_holds(tmp_path) -> None:
    """A strict node and a paid-for advisory are admitted; an unpaid one is not."""
    # A node that ships strict is admitted.
    assert check_node(CONVENTION["rules"][0]) == []

    # A node that ships advisory WITH a precondition and a discharging issue is admitted.
    assert check_node(CONVENTION["rules"][1]) == []

    # Over a whole repository: this train's convention passes, and the foreign one — which
    # is advisory and unpaid — is left entirely alone.
    _write(tmp_path, "coder", "projection", CONVENTION)
    _write(tmp_path, "coach", "legacy", FOREIGN)

    report = scan_conventions(tmp_path)
    assert report.ok, report.render()
    assert report.checked == 2  # this train's two nodes; the foreign convention is not scanned
    assert "ships strict" in report.render()

    # Take the payment away, and the same node is refused.
    unpaid = {
        **CONVENTION,
        "rules": [
            CONVENTION["rules"][0],
            {"id": "coder.projection.no-host-paths", "disposition": "advisory"},
        ],
    }
    _write(tmp_path, "coder", "projection", unpaid)

    report = scan_conventions(tmp_path)
    assert not report.ok
    assert [v.rule_id for v in report.violations] == ["coder.projection.no-host-paths"]
    assert report.violations[0].clause == dispositions.CLAUSE_UNPAID_ADVISORY
    assert report.violations[0].source == "projection.convention.yaml"

    # The rollup the CLI prints says the same thing in machine-readable form.
    summary = dispositions.summary(tmp_path)
    assert summary["train"] == TRAIN_ID
    assert summary["ok"] is False
    assert summary["violations"][0]["clause"] == dispositions.CLAUSE_UNPAID_ADVISORY
