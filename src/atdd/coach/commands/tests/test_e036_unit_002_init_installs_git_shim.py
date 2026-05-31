# URN: test:govern-lifecycle:agnostic-git-config-bare-guard-via-path-shim:E036-UNIT-002-init-installs-git-shim
# Acceptance: acc:govern-lifecycle:E036-UNIT-002-init-installs-git-shim
# WMBT: wmbt:govern-lifecycle:E036
# Phase: RED
# Layer: backend.integration
"""AC-UNIT-002: atdd init installs .atdd/bin/git from the git.shim template.

Drives ProjectInitializer.install_path_shim_enforcement() — the existing gh-shim
install surface (#816) — which now ALSO installs the agent-agnostic `git` shim
alongside the gh shim and the shared `.envrc` PATH_add line.

RED state: src/atdd/coach/templates/bin/git.shim does not exist and
install_path_shim_enforcement() does not yet install .atdd/bin/git.
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
GIT_SHIM_TEMPLATE = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "bin" / "git.shim"


def test_init_installs_git_shim_and_envrc(tmp_path: Path) -> None:
    assert GIT_SHIM_TEMPLATE.exists(), f"RED: {GIT_SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"

    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)

    initializer = ProjectInitializer(target_dir=repo)
    initializer.install_path_shim_enforcement()

    git_shim = repo / ".atdd" / "bin" / "git"
    envrc = repo / ".envrc"
    assert git_shim.exists(), ".atdd/bin/git was not installed"
    assert os.access(git_shim, os.X_OK), ".atdd/bin/git is not executable"
    assert git_shim.read_text() == GIT_SHIM_TEMPLATE.read_text(), ".atdd/bin/git does not match the template"
    assert envrc.exists() and "PATH_add .atdd/bin" in envrc.read_text(), ".envrc missing `PATH_add .atdd/bin`"
