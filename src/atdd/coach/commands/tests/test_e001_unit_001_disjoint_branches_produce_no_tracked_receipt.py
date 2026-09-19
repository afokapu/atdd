# acc:verify-validation-receipt:E001-UNIT-001-disjoint-branches-produce-no-tracked-receipt
"""RED acceptance for wmbt:verify-validation-receipt:E001.

The validation pass-receipt must be a local, gitignored dev cache — never a
tracked file — so two branches validating disjoint work cannot three-way
conflict on it (#1566). This test pins that the receipt the writer targets is
matched by a .gitignore rule.

Fails today because .atdd/baselines/validation/ is tracked, not ignored.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from atdd.coach.commands.validation_baseline import validation_baseline_path
from atdd.coach.utils.repo import find_repo_root


def _is_git_ignored(repo_root: Path, rel: str) -> bool:
    """True iff `rel` is matched by a gitignore rule in `repo_root`."""
    result = subprocess.run(
        ["git", "check-ignore", rel],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    # git check-ignore exits 0 when the path IS ignored, 1 when it is not.
    return result.returncode == 0


def test_receipt_path_is_gitignored():
    repo_root = find_repo_root()
    receipt = validation_baseline_path(repo_root, "all")
    rel = receipt.relative_to(repo_root).as_posix()

    assert _is_git_ignored(repo_root, rel), (
        f"{rel} is NOT gitignored — the pass-receipt is still tracked whole-tree "
        f"state that every concurrent branch rewrites and collides on (#1566). "
        f"Option A: git-rm the receipts and gitignore .atdd/baselines/validation/."
    )
