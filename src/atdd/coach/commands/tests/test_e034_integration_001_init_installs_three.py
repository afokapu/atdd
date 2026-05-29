# URN: test:govern-lifecycle:gh-issue-create-block-l3:E034-INTEGRATION-001-init-installs-three
# Acceptance: acc:govern-lifecycle:E034-INTEGRATION-001-init-installs-three
# WMBT: wmbt:govern-lifecycle:E034
# Phase: RED
# Layer: backend.integration
"""AC-INTEGRATION-001: atdd init installs the shim, .envrc, and pre-commit hook idempotently.

Drives ProjectInitializer.install_path_shim_enforcement() (the public contract the
coder implements and wires into init()): a fresh worktree gains an executable
.atdd/bin/gh, a .envrc with `PATH_add .atdd/bin`, and a gh-issue-create pre-commit
hook; a second run does not duplicate the PATH_add line or clobber operator edits.

RED state: the gh.shim / pre-commit templates do not exist and
ProjectInitializer has no install_path_shim_enforcement method yet.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.initializer import ProjectInitializer
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach]

REPO_ROOT = find_repo_root()
SHIM_TEMPLATE = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "bin" / "gh.shim"
HOOK_TEMPLATE = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks" / "pre-commit-gh-issue-create.sh"


def _hook_installed(repo: Path) -> bool:
    """True when the gh-issue-create pre-commit enforcement is installed anywhere git runs it."""
    candidates = [
        repo / ".git" / "hooks" / "pre-commit",
        repo / ".git" / "hooks" / "pre-commit-gh-issue-create.sh",
        repo / ".atdd" / "hooks" / "pre-commit",
        repo / ".atdd" / "hooks" / "pre-commit-gh-issue-create.sh",
    ]
    for path in candidates:
        if path.exists() and "gh" in path.read_text() and "issue" in path.read_text():
            return True
    return False


def test_init_installs_shim_envrc_and_hook_idempotently(tmp_path: Path) -> None:
    # RED fast-fail: the templates and install surface do not exist yet.
    assert SHIM_TEMPLATE.exists(), f"RED: {SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"
    assert HOOK_TEMPLATE.exists(), f"RED: {HOOK_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"

    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)

    initializer = ProjectInitializer(target_dir=repo)
    assert hasattr(initializer, "install_path_shim_enforcement"), (
        "RED: ProjectInitializer.install_path_shim_enforcement() not implemented yet"
    )

    initializer.install_path_shim_enforcement()

    shim = repo / ".atdd" / "bin" / "gh"
    envrc = repo / ".envrc"
    assert shim.exists(), ".atdd/bin/gh was not installed"
    assert os.access(shim, os.X_OK), ".atdd/bin/gh is not executable"
    assert envrc.exists(), ".envrc was not written"
    assert "PATH_add .atdd/bin" in envrc.read_text(), ".envrc missing `PATH_add .atdd/bin`"
    assert _hook_installed(repo), "gh-issue-create pre-commit hook was not installed"

    # Idempotent: second run must not duplicate the PATH_add line.
    initializer.install_path_shim_enforcement()
    path_add_lines = [ln for ln in envrc.read_text().splitlines() if ln.strip() == "PATH_add .atdd/bin"]
    assert len(path_add_lines) == 1, f"PATH_add line duplicated on re-run: {path_add_lines!r}"
