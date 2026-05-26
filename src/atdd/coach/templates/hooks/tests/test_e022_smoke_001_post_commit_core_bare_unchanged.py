# URN: test:govern-lifecycle:close-substrate-friction-regressions:E022-SMOKE-001-post-commit-leaves-core-bare-unchanged
# Acceptance: acc:govern-lifecycle:E022-SMOKE-001-post-commit-leaves-core-bare-unchanged
# WMBT: wmbt:govern-lifecycle:E022
# Phase: RED
# Layer: backend.integration
"""
AC-SMOKE-001: after committing a coach-path file and waiting for the post-commit hook
to complete, core.bare equals its pre-commit value.

RED state: The post-commit hook does not yet exclude SMOKE tests or trap core.bare.
When this test runs against a real tmp_path repo with the current hook, the inner
SMOKE test (test_guard_catches_real_live_repo_contamination) would be excluded
eventually — but the trap is not present yet, so an interrupted run can leave
core.bare contaminated. This test stub is written RED to drive the implementation.
"""
from __future__ import annotations

import subprocess
import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.slow]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_TEMPLATE = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks" / "post-commit"


def _git(tmp: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(tmp), *args],
        capture_output=True,
        text=True,
    )


def _setup_repo(tmp: Path) -> None:
    _git(tmp, "init", "-q", "-b", "main")
    _git(tmp, "config", "user.email", "test@test.com")
    _git(tmp, "config", "user.name", "Test")
    hooks_dir = tmp / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_dest = hooks_dir / "post-commit"
    hook_dest.write_text(HOOK_TEMPLATE.read_text(encoding="utf-8"))
    hook_dest.chmod(0o755)
    # Create an initial commit so HEAD exists
    (tmp / "README.md").write_text("init")
    _git(tmp, "add", "README.md")
    _git(tmp, "commit", "-m", "init", "--no-verify")


def test_post_commit_hook_leaves_core_bare_unchanged(tmp_path: Path):
    """AC-SMOKE-001: post-commit hook must not change core.bare from its pre-commit value."""
    _setup_repo(tmp_path)

    bare_before = _git(tmp_path, "config", "core.bare").stdout.strip()

    # Commit a dummy file (simulating a coach-path change)
    coach_dir = tmp_path / "src" / "atdd" / "coach" / "commands"
    coach_dir.mkdir(parents=True, exist_ok=True)
    (coach_dir / "dummy.py").write_text("# dummy")
    _git(tmp_path, "add", "src")
    result = _git(tmp_path, "commit", "-m", "test: add dummy coach file")

    bare_after = _git(tmp_path, "config", "core.bare").stdout.strip()

    assert bare_before == bare_after, (
        f"Post-commit hook changed core.bare!\n"
        f"  before: {bare_before!r}\n"
        f"  after:  {bare_after!r}\n"
        f"Hook stderr: {result.stderr}\n"
        "The hook must restore core.bare to its pre-commit value even when the\n"
        "inner pytest session sets it (issue #845 Item A)."
    )
