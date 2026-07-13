# URN: test:migrate-projection-authority:migrate-manifest-projection:C001-UNIT-001-refuses-before-any-write
# Acceptance: acc:migrate-projection-authority:C001-UNIT-001-refuses-before-any-write
# WMBT: wmbt:migrate-projection-authority:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A manifest whose third entry has no uid and whose fifth duplicates the first's aborts the WHOLE run — the tool exits non-zero and not one file appears under .atdd/state/projection/. Refs #1434.
"""An unmigratable manifest entry aborts the run before the first write (C001-UNIT-001).

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C001

A migration that half-succeeds leaves a projection tree that is neither the old truth nor the
new one, and the operator's next move — re-run? revert? hand-fix? — depends on facts the tool
destroyed on its way out. So the refusal must precede *every* write, not merely the write of the
offending entry: the four healthy entries around the bad one must not appear either.
Refs #1434 / #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.manifest_migration import LossyMigrationError, migrate
from atdd.state.projection import PROJECTION_RELATIVE

from ._helpers import UID_A, UID_B, control_root, entry, projection_files, write_manifest


def test_c001_unit_001_refuses_before_any_write(tmp_path) -> None:
    """A missing uid and a duplicate uid abort the whole run; the projection tree stays absent."""
    root = control_root(tmp_path / "repo")
    write_manifest(root, [
        entry("first", uid=UID_A, phase="PLANNED"),
        entry("second", uid=UID_B, phase="GREEN"),
        entry("third-no-uid", phase="RED"),          # (3) carries no uid
        entry("fourth", uid="wi_01HF7YAT00M78607F000000004", phase="INIT"),
        entry("fifth-dupe", uid=UID_A, phase="SMOKE"),  # (5) duplicates the first's uid
    ])

    with pytest.raises(LossyMigrationError) as caught:
        migrate(root)

    # Both defects are named — and the run stopped for them, not merely noticed them.
    assert len(caught.value.defects) == 2
    assert {defect.index for defect in caught.value.defects} == {2, 4}

    # Nothing was written. Not the offending entries, and — the part that matters — not the three
    # healthy ones beside them. A projection tree that exists at all here is a failure.
    assert projection_files(root) == []
    assert not (root / PROJECTION_RELATIVE).exists()
