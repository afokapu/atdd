# Acceptance: acc:integration-hardening:C002-UNIT-003-pre-commit-blocks-mass-delete
# Acceptance: acc:integration-hardening:C002-UNIT-004-pre-commit-allows-explicit-decom
"""Unit tests for the pre-commit mass-delete contamination guard (#629 Layer 2).

Background: bare-mode contamination first manifests at commit time as a
``git add -A`` that stages thousands of deletions. Layer 2 catches that
signature at the earliest possible runtime gate. Override env var:
``ATDD_SKIP_MASSDELETE=1`` for the rare legitimate decommission case.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src/atdd/coach/templates/hooks/pre-commit"

# How many files we stage as deletions to comfortably cross the >50 threshold.
MASS_DELETE_FILE_COUNT = 60


def _init_repo_with_files(tmp_path: Path, file_count: int = MASS_DELETE_FILE_COUNT) -> None:
    """Init a non-bare git repo on a feature branch, populate + commit ``file_count`` files.

    Test hygiene: every git command takes explicit ``-C str(tmp_path)``. We
    never inherit cwd or touch the invoking process's repo.
    """
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    # Configure committer identity for the temp repo (no global leakage).
    for k, v in (("user.email", "test@atdd.test"), ("user.name", "atdd test")):
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", k, v],
            check=True,
            capture_output=True,
        )

    # Create file_count files and commit them — this is the baseline we will
    # then delete in the staged diff.
    for i in range(file_count):
        (tmp_path / f"file_{i:03d}.txt").write_text(f"content {i}\n")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "."],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "seed"],
        check=True,
        capture_output=True,
    )

    # Switch off main so the hook's main-block check does not trip.
    subprocess.run(
        ["git", "-C", str(tmp_path), "checkout", "-q", "-b", "feat/test-mass-delete"],
        check=True,
        capture_output=True,
    )


def _stage_mass_delete(tmp_path: Path) -> None:
    """Stage deletions of all the seeded files."""
    for f in tmp_path.glob("file_*.txt"):
        f.unlink()
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "-A"],
        check=True,
        capture_output=True,
    )


def _write_commit_msg(tmp_path: Path, msg: str) -> Path:
    """Write COMMIT_EDITMSG into the repo's .git directory."""
    commit_msg_path = tmp_path / ".git" / "COMMIT_EDITMSG"
    commit_msg_path.parent.mkdir(parents=True, exist_ok=True)
    commit_msg_path.write_text(msg)
    return commit_msg_path


def _run_hook(
    tmp_path: Path, commit_msg_path: Path, env: dict | None = None
) -> subprocess.CompletedProcess:
    """Execute pre-commit. Passes the COMMIT_EDITMSG path as $1 (git's interface for prepare-commit-msg, but pre-commit accepts it too)."""
    full_env = {
        **os.environ,
        "ATDD_SKIP_MANIFEST_CHECK": "1",
    }
    if env:
        full_env.update(env)
    return subprocess.run(
        ["sh", str(HOOK_PATH), str(commit_msg_path)],
        cwd=str(tmp_path),
        env=full_env,
        capture_output=True,
        text=True,
    )


def test_pre_commit_blocks_mass_delete_without_prefix(tmp_path: Path) -> None:
    """C002-UNIT-003: >50 staged deletions without a decom prefix is blocked."""
    _init_repo_with_files(tmp_path)
    _stage_mass_delete(tmp_path)
    msg = _write_commit_msg(tmp_path, "fix: unrelated bugfix\n")

    result = _run_hook(tmp_path, msg)

    assert result.returncode != 0, (
        f"pre-commit must block a mass-delete without decom prefix; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )
    assert "mass-delete" in result.stderr.lower() or "delete" in result.stderr.lower(), (
        f"stderr must reference the mass-delete block; got:\n{result.stderr}"
    )


def test_pre_commit_skip_env_overrides_mass_delete(tmp_path: Path) -> None:
    """C002-UNIT-003 (override): ATDD_SKIP_MASSDELETE=1 lets the commit through the mass-delete check."""
    _init_repo_with_files(tmp_path)
    _stage_mass_delete(tmp_path)
    msg = _write_commit_msg(tmp_path, "fix: unrelated bugfix\n")

    result = _run_hook(tmp_path, msg, env={"ATDD_SKIP_MASSDELETE": "1"})

    assert "mass-delete" not in result.stderr.lower(), (
        f"ATDD_SKIP_MASSDELETE=1 must suppress the mass-delete block; got:\n{result.stderr}"
    )


def test_pre_commit_allows_chore_decom_prefix(tmp_path: Path) -> None:
    """C002-UNIT-004: a chore(decom): commit message lets the mass-delete through."""
    _init_repo_with_files(tmp_path)
    _stage_mass_delete(tmp_path)
    msg = _write_commit_msg(tmp_path, "chore(decom): remove deprecated module X\n")

    result = _run_hook(tmp_path, msg)

    assert "mass-delete" not in result.stderr.lower(), (
        f"chore(decom): prefix must bypass the mass-delete block; got:\n{result.stderr}"
    )


def test_pre_commit_allows_refactor_remove_prefix(tmp_path: Path) -> None:
    """C002-UNIT-004: refactor(remove): also bypasses the mass-delete block."""
    _init_repo_with_files(tmp_path)
    _stage_mass_delete(tmp_path)
    msg = _write_commit_msg(tmp_path, "refactor(remove): kill dead code path\n")

    result = _run_hook(tmp_path, msg)

    assert "mass-delete" not in result.stderr.lower(), (
        f"refactor(remove): prefix must bypass the mass-delete block; got:\n{result.stderr}"
    )


def test_pre_commit_allows_mass_delete_approved_token(tmp_path: Path) -> None:
    """C002-UNIT-004: [mass-delete-approved] anywhere in the body bypasses the block."""
    _init_repo_with_files(tmp_path)
    _stage_mass_delete(tmp_path)
    msg = _write_commit_msg(
        tmp_path,
        "chore: cleanup\n\nBody with [mass-delete-approved] token.\n",
    )

    result = _run_hook(tmp_path, msg)

    assert "mass-delete" not in result.stderr.lower(), (
        f"[mass-delete-approved] token must bypass the mass-delete block; got:\n{result.stderr}"
    )


def test_pre_commit_passes_normal_commit(tmp_path: Path) -> None:
    """Sanity check: a small (1-file) normal commit is not affected by the mass-delete check."""
    _init_repo_with_files(tmp_path, file_count=1)
    (tmp_path / "file_000.txt").unlink()
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "-A"],
        check=True,
        capture_output=True,
    )
    msg = _write_commit_msg(tmp_path, "fix: remove one file\n")

    result = _run_hook(tmp_path, msg)

    assert "mass-delete" not in result.stderr.lower(), (
        f"a normal single-file commit must not trigger the mass-delete block; got:\n{result.stderr}"
    )
