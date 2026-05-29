"""Shared fixtures for the .atdd/bin/gh PATH-shim template tests (issue #816).

The shim source lives at src/atdd/coach/templates/bin/gh.shim and is installed
to ``.atdd/bin/gh`` by ``atdd init``. These fixtures install the on-disk shim
into a tmp worktree and place a *recording* gh stub later on PATH so a forwarded
call is observable. RED state: the template does not exist yet, so ``install_shim``
asserts its presence and fails with an explicit RED message until GREEN lands it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root

REPO_ROOT = find_repo_root()
SHIM_TEMPLATE = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "bin" / "gh.shim"


def install_shim(worktree: Path) -> Path | None:
    """Copy the gh.shim template to <worktree>/.atdd/bin/gh (mode 0755).

    Best-effort: when the template does not exist yet (RED), the shim dir is
    still created (empty) and None is returned, so the fixture never errors in
    setup — each test asserts ``SHIM_TEMPLATE.exists()`` for a clean RED FAIL.
    """
    bin_dir = worktree / ".atdd" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    if not SHIM_TEMPLATE.exists():
        return None
    dst = bin_dir / "gh"
    shutil.copy(SHIM_TEMPLATE, dst)
    dst.chmod(0o755)
    return dst


def make_recording_gh(bin_dir: Path) -> Path:
    """Create a recording ``gh`` stub in *bin_dir* that logs argv and exits 0.

    Returns the path to the call-log file (one line per forwarded invocation).
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    record = bin_dir / "gh_calls.log"
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{record}"\n'
        "exit 0\n"
    )
    gh.chmod(0o755)
    return record


def run_gh_via_shim(worktree: Path, real_bin_dir: Path, args: list[str]) -> subprocess.CompletedProcess:
    """Invoke ``gh <args>`` with PATH=<worktree>/.atdd/bin:<real_bin_dir>:... and cwd=worktree."""
    env = {**os.environ}
    shim_dir = worktree / ".atdd" / "bin"
    env["PATH"] = f"{shim_dir}:{real_bin_dir}:{env.get('PATH', '')}"
    return subprocess.run(
        ["gh", *args],
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


@pytest.fixture()
def shim_worktree(tmp_path: Path):
    """Return (worktree, real_bin_dir, record_path) with the shim installed and a recording gh staged."""
    worktree = tmp_path / "wt"
    worktree.mkdir()
    install_shim(worktree)
    real_bin = tmp_path / "realbin"
    record = make_recording_gh(real_bin)
    return worktree, real_bin, record
