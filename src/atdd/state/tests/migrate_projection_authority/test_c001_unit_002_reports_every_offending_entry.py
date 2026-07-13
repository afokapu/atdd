# URN: test:migrate-projection-authority:migrate-manifest-projection:C001-UNIT-002-reports-every-offending-entry
# Acceptance: acc:migrate-projection-authority:C001-UNIT-002-reports-every-offending-entry
# WMBT: wmbt:migrate-projection-authority:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A manifest with three distinct defects — a missing uid, a duplicate uid, and an unknown phase — is refused with ALL THREE named, each with its offending field and reason; the projection directory is unchanged. Refs #1434.
"""The refusal names every offending entry, not the first (C001-UNIT-002).

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: GREEN
WMBT: wmbt:migrate-projection-authority:C001

A tool that reports one defect per run turns a five-minute manifest fix into five runs, and an
operator who has been told about one defect reasonably believes there is one. Every offending
entry, its offending field, and the reason — in a single refusal. Refs #1434 / #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.manifest_migration import (
    DEFECT_DUPLICATE_UID,
    DEFECT_MISSING_UID,
    DEFECT_UNKNOWN_PHASE,
    LossyMigrationError,
    inspect,
    migrate,
)

from ._helpers import UID_A, UID_B, control_root, entry, projection_files, write_manifest


def _sessions():
    return [
        entry("clean", uid=UID_A, phase="PLANNED"),
        entry("no-uid", phase="GREEN"),                        # defect 1
        entry("dupe", uid=UID_A, phase="RED"),                 # defect 2
        entry("bad-phase", uid=UID_B, phase="MARINATING"),     # defect 3
    ]


def test_c001_unit_002_reports_every_offending_entry(tmp_path) -> None:
    """All three defects are reported at once, each naming its entry, field and reason."""
    root = control_root(tmp_path / "repo")
    write_manifest(root, _sessions())

    # Seed a projection directory with a file that must survive untouched: "unchanged" is a
    # stronger claim than "absent", and it is the one an operator re-running a failed migration
    # over an existing tree actually depends on.
    projection = root / ".atdd" / "state" / "projection"
    projection.mkdir(parents=True)
    survivor = projection / "wi_01HF7YAT00M78607F000000009.yaml"
    survivor.write_bytes(b"uid: pre-existing\n")
    before = survivor.read_bytes()

    with pytest.raises(LossyMigrationError) as caught:
        migrate(root)

    defects = caught.value.defects
    assert len(defects) == 3, [d.render() for d in defects]

    by_rule = {defect.rule: defect for defect in defects}
    assert set(by_rule) == {DEFECT_MISSING_UID, DEFECT_DUPLICATE_UID, DEFECT_UNKNOWN_PHASE}

    # Each names its entry, its offending FIELD, and a reason — not just "invalid".
    assert by_rule[DEFECT_MISSING_UID].slug == "no-uid"
    assert by_rule[DEFECT_MISSING_UID].field == "uid"
    assert by_rule[DEFECT_DUPLICATE_UID].slug == "dupe"
    assert UID_A in by_rule[DEFECT_DUPLICATE_UID].reason
    assert by_rule[DEFECT_UNKNOWN_PHASE].slug == "bad-phase"
    assert by_rule[DEFECT_UNKNOWN_PHASE].field == "status"
    assert "MARINATING" in by_rule[DEFECT_UNKNOWN_PHASE].reason

    # The single rendered message carries all three, so an operator reading stderr sees the lot.
    rendered = str(caught.value)
    for slug in ("no-uid", "dupe", "bad-phase"):
        assert slug in rendered

    # The projection directory is UNCHANGED: no new file, and the pre-existing one is byte-identical.
    assert projection_files(root) == [survivor.name]
    assert survivor.read_bytes() == before

    # `inspect` is the pure half, and it agrees — the refusal is a decision, not a side effect.
    assert len(inspect(_sessions())) == 3
