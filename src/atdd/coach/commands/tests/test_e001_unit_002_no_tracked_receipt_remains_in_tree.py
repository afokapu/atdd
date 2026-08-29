# acc:verify-validation-receipt:E001-UNIT-002-no-tracked-receipt-remains-in-tree
"""RED acceptance for wmbt:verify-validation-receipt:E001.

The previously committed .atdd/baselines/validation/*.yaml receipts must be
removed from version control — nothing in CI reads them (only cli.py), so they
buy no merge-time assurance while forcing a false-receipt conflict on every
concurrent merge (#1566).

Fails today because five receipt files are tracked by git.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from atdd.coach.utils.repo import find_repo_root


def _tracked_receipts(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", ".atdd/baselines/validation/"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def test_no_validation_receipts_are_tracked():
    repo_root = find_repo_root()
    tracked = _tracked_receipts(repo_root)

    assert tracked == [], (
        "These validation pass-receipts are still tracked by git and will "
        f"reconflict on every concurrent merge (#1566): {tracked}"
    )
