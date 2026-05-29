# URN: test:govern-lifecycle:gh-issue-create-block-l3:E034-SMOKE-001-real-init-installs-and-warns
# Acceptance: acc:govern-lifecycle:E034-SMOKE-001-real-init-installs-and-warns
# WMBT: wmbt:govern-lifecycle:E034
# Phase: RED
# Layer: backend.integration
"""AC-SMOKE-001: a real `atdd init` installs the three artifacts and soft-fails on missing direnv.

Drives the actual CLI entry point as a subprocess in a real tmp git repo with a
PATH that lacks `direnv`: init must exit 0 (warn, not error), leave .atdd/bin/gh,
.envrc, and the pre-commit hook on disk, and print a direnv warning.

RED state: the gh.shim template does not exist yet, so the fast-fail existence
assertion fails before any subprocess runs (no network / no hang in RED).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach]

REPO_ROOT = find_repo_root()
SHIM_TEMPLATE = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "bin" / "gh.shim"


def _path_without_direnv() -> str:
    """Return a PATH string with any directory that contains a `direnv` binary removed."""
    kept = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        if (Path(entry) / "direnv").exists():
            continue
        kept.append(entry)
    return os.pathsep.join(kept)


def test_real_atdd_init_installs_and_warns_on_missing_direnv(tmp_path: Path) -> None:
    # RED fast-fail before spawning any subprocess (avoids network/hang in RED).
    assert SHIM_TEMPLATE.exists(), f"RED: {SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"

    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)

    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "PATH": _path_without_direnv()}
    result = subprocess.run(
        ["atdd", "init"],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, f"atdd init did not soft-fail cleanly (exit {result.returncode}):\n{combined}"
    assert (repo / ".atdd" / "bin" / "gh").exists(), ".atdd/bin/gh missing after real init"
    assert (repo / ".envrc").exists(), ".envrc missing after real init"
    assert "PATH_add .atdd/bin" in (repo / ".envrc").read_text(), ".envrc missing PATH_add line"
    assert "direnv" in combined.lower(), f"no direnv warning surfaced: {combined!r}"
