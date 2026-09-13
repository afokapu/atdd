# Acceptance: acc:govern-lifecycle:E009-SMOKE-002-a-real-passing-validate-leaves-the-tree-clean
# Phase: RED
# Layer: smoke
# Assertion: behavioral
"""E009-SMOKE-002 — a passing validate must not dirty the working tree.

The defect is observed as a dirty tree seconds after a commit: the post-commit
hook runs ``atdd validate``, the run passes, and the writer rewrites
``.atdd/baselines/validation/<phase>.yaml`` with a fresh ``passed_at``. Measured
on this repo: 66 commits in 90 days touched those files, 55 of them riding along
with unrelated work, and one became the only merge conflict in PR #1955.

So the proof has to be the REAL writer against a REAL git repo — a mocked path
would prove only that a stub was called. The receipts must still land on disk,
because local use of ``--verify-baseline`` is unaffected by this issue; what
must change is that git stops seeing them.

HERMETIC: a throwaway ``git init`` under tmp_path. No network, no real repo.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.initializer import ProjectInitializer
from atdd.coach.commands.validation_baseline import (
    PHASES,
    write_validation_baseline,
)

pytestmark = [pytest.mark.coach]


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True
    )
    for key, value in (("user.email", "validator@atdd.test"), ("user.name", "ATDD Validator")):
        subprocess.run(["git", "config", key, value], cwd=repo, check=True, capture_output=True)
    return repo


def test_a_real_passing_validate_leaves_the_tree_clean(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ProjectInitializer(target_dir=repo)._seed_gitignore_entries()

    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"], cwd=repo, check=True, capture_output=True
    )

    before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert before == "", f"Fixture not clean before the writer ran: {before!r}"

    # The real writer, once per phase — exactly what a passing validate does.
    for phase in PHASES:
        write_validation_baseline(phase=phase, repo_root=repo, could_not_check=0)

    for phase in PHASES:
        receipt = repo / ".atdd" / "baselines" / "validation" / f"{phase}.yaml"
        assert receipt.is_file(), (
            f"{receipt.name} was not written — local `--verify-baseline` must keep working"
        )

    after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert after == "", (
        "A passing validate dirtied the working tree:\n"
        f"{after}"
        "Every commit, rebase and push now needs `git checkout -- .atdd/` first."
    )
