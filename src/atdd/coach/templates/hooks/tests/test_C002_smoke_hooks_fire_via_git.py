# Acceptance: acc:integration-hardening:C002-SMOKE-001-pre-push-fires-on-real-git-push
# Acceptance: acc:integration-hardening:C002-SMOKE-002-commit-msg-fires-on-real-git-commit
"""SMOKE tests: the hooks fire via real git invocation, not just direct sh execution.

The UNIT tests in the sibling files exercise the hook scripts in
isolation (``sh hookpath ...``). These SMOKE tests verify that the
hooks fire through git's own trigger plumbing — i.e. that the install
mode (chmod +x, ``.git/hooks/<name>`` placement) actually catches the
contamination signatures when an operator runs ``git commit`` or
``git push`` for real.

Failure modes these would catch that UNIT tests miss:
- hook file not executable after installation
- hook fails when git invokes it via ``$SHELL`` instead of ``sh``
- hook script has a feature that works in a direct ``sh`` invocation
  but not when git sets up the hook environment (env vars, cwd, stdin)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOKS_DIR = REPO_ROOT / "src/atdd/coach/templates/hooks"


def _init_local_and_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Create a local non-bare repo + an adjacent bare repo we can push to.

    Hygiene: every git command takes explicit ``-C str(path)``. The
    bare repo is created in a sibling dir to the local one — never in
    cwd, never in tmp_path itself.
    """
    local = tmp_path / "local"
    remote = tmp_path / "remote.git"

    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(local)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "init", "-q", "--bare", str(remote)],
        check=True,
        capture_output=True,
    )

    for k, v in (("user.email", "test@atdd.test"), ("user.name", "atdd test")):
        subprocess.run(
            ["git", "-C", str(local), "config", k, v],
            check=True,
            capture_output=True,
        )

    subprocess.run(
        ["git", "-C", str(local), "remote", "add", "origin", str(remote)],
        check=True,
        capture_output=True,
    )

    return local, remote


def _install_hook(local: Path, hook_name: str) -> None:
    """Copy the named hook template into the local repo's .git/hooks/ and chmod +x.

    This mirrors what ``atdd init``'s ``_install_hooks`` does, except
    using a per-repo .git/hooks/ rather than the shared
    .atdd/hooks/ + core.hooksPath. Either install path triggers the
    same git invocation flow.
    """
    src = HOOKS_DIR / hook_name
    dst = local / ".git" / "hooks" / hook_name
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    dst.chmod(0o755)


def _make_seed_commit(local: Path, file_count: int = 60) -> None:
    """Create file_count files, commit them, then branch off main."""
    for i in range(file_count):
        (local / f"file_{i:03d}.txt").write_text(f"content {i}\n")
    subprocess.run(
        ["git", "-C", str(local), "add", "."],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(local), "commit", "-q", "-m", "seed"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(local), "checkout", "-q", "-b", "feat/smoke-test"],
        check=True,
        capture_output=True,
    )


def test_pre_push_fires_when_git_push_runs_with_core_bare_true(tmp_path: Path) -> None:
    """C002-SMOKE-001: real ``git push`` against a contaminated repo is blocked by the hook."""
    local, _remote = _init_local_and_remote(tmp_path)
    _make_seed_commit(local)
    _install_hook(local, "pre-push")

    # Mark the local repo as bare-mode contaminated, then attempt push.
    subprocess.run(
        ["git", "-C", str(local), "config", "core.bare", "true"],
        check=True,
        capture_output=True,
    )

    env = {**os.environ, "CI": "true", "ATDD_SKIP_VERSION_GATE": "1"}
    result = subprocess.run(
        ["git", "-C", str(local), "push", "origin", "feat/smoke-test"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, (
        f"git push must be blocked by the pre-push hook when core.bare=true; "
        f"rc={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "core.bare" in result.stderr.lower() or "bare-mode" in result.stderr.lower(), (
        f"push rejection must mention bare-mode contamination; got:\n{result.stderr}"
    )


def test_commit_msg_fires_when_git_commit_runs_with_mass_delete(tmp_path: Path) -> None:
    """C002-SMOKE-002: real ``git commit`` against a mass-delete diff is blocked by the hook."""
    local, _remote = _init_local_and_remote(tmp_path)
    _make_seed_commit(local, file_count=60)
    _install_hook(local, "commit-msg")

    # Stage a mass-delete diff (60 file deletions).
    for f in local.glob("file_*.txt"):
        f.unlink()
    subprocess.run(
        ["git", "-C", str(local), "add", "-A"],
        check=True,
        capture_output=True,
    )

    result = subprocess.run(
        ["git", "-C", str(local), "commit", "-m", "fix: unrelated bugfix"],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, (
        f"git commit must be blocked by the commit-msg hook on mass-delete; "
        f"rc={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "mass-delete" in result.stderr.lower() or "delete" in result.stderr.lower(), (
        f"commit rejection must mention mass-delete; got:\n{result.stderr}"
    )


def test_commit_msg_allows_chore_decom_via_git_commit(tmp_path: Path) -> None:
    """C002-SMOKE-002 (positive): real ``git commit`` with a chore(decom): prefix succeeds despite mass-delete."""
    local, _remote = _init_local_and_remote(tmp_path)
    _make_seed_commit(local, file_count=60)
    _install_hook(local, "commit-msg")

    for f in local.glob("file_*.txt"):
        f.unlink()
    subprocess.run(
        ["git", "-C", str(local), "add", "-A"],
        check=True,
        capture_output=True,
    )

    result = subprocess.run(
        ["git", "-C", str(local), "commit", "-m", "chore(decom): remove obsolete fixture files"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"git commit with chore(decom): prefix must NOT be blocked; "
        f"rc={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
