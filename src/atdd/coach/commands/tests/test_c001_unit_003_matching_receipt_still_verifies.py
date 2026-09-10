# acc:verify-validation-receipt:C001-UNIT-003-matching-receipt-still-verifies
"""Discriminating control for wmbt:verify-validation-receipt:C001.

The reject in C001-UNIT-001/002 must be discriminating, not blanket-failing: a
receipt whose recorded source_hash matches the current tree (and version) must
still verify as PASS. Without this control, a verify that rejects everything
would satisfy the reject tests while being useless.

This also pins reproducibility (see E002): a receipt written for the current
tree must verify against that same tree in the same environment.
"""
from __future__ import annotations

from atdd.coach.commands.validation_baseline import (
    verify_validation_baseline,
    write_validation_baseline,
)

_PHASE = "coach"


def test_unmutated_receipt_verifies_pass(tmp_path):
    write_validation_baseline(_PHASE, skipped_api=False, repo_root=tmp_path)

    rc = verify_validation_baseline(phase=_PHASE, repo_root=tmp_path)
    assert rc == 0, (
        "a freshly written, unmutated receipt failed verify-on-read against the "
        "same tree it was written for — verify is not reproducible (see E002)"
    )
