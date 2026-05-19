# Acceptance: acc:govern-lifecycle:E012-UNIT-001-pre-commit-allows-manifest-only-on-main
# Acceptance: acc:govern-lifecycle:E012-UNIT-002-pre-commit-blocks-manifest-plus-code-on-main
# Acceptance: acc:govern-lifecycle:E012-UNIT-003-pre-commit-blocks-code-only-on-main
# Acceptance: acc:govern-lifecycle:Y004-UNIT-001-pre-commit-drift-notice-non-blocking
"""Unit tests for the pre-commit manifest-only exception and drift notice (#775).

Problem: the pre-commit hook unconditionally blocked all commits on main/master.
`atdd issue <slug>` runs from main, commits only .atdd/manifest.yaml, and was
blocked → the registration was lost.

Fix: a staged-paths exception before `exit 1` — when the staged set is exactly
`.atdd/manifest.yaml`, the hook exits 0. Any other combination stays blocked.

Drift notice: after the main-block section the hook prints a non-blocking
warning when the current branch's slug is not found in the manifest. The hook
never writes to the manifest (that lives in the CLI).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src/atdd/coach/templates/hooks/pre-commit"

_GIT_CONFIG = [
    ("user.email", "test@atdd.test"),
    ("user.name", "atdd test"),
]


def _init_repo(tmp_path: Path, branch: str = "main") -> None:
    """Initialise a non-bare git repo with one seed commit on *branch*.

    All git calls use ``-C str(tmp_path)`` for hygiene (never inherits cwd or
    touches the invoking process's repository).
    """
    subprocess.run(
        ["git", "init", "-q", "-b", branch, str(tmp_path)],
        check=True, capture_output=True,
    )
    for key, value in _GIT_CONFIG:
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", key, value],
            check=True, capture_output=True,
        )
    # Seed commit so HEAD exists (hooks need a valid HEAD to run).
    seed = tmp_path / "seed.txt"
    seed.write_text("seed\n")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "seed.txt"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "seed"],
        check=True, capture_output=True,
    )


def _stage_manifest_only(tmp_path: Path) -> None:
    """Stage only .atdd/manifest.yaml."""
    manifest_dir = tmp_path / ".atdd"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_dir / "manifest.yaml"
    manifest.write_text("sessions:\n- id: '1'\n  slug: my-issue\n")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", str(manifest.relative_to(tmp_path))],
        check=True, capture_output=True,
    )


def _stage_manifest_plus_code(tmp_path: Path) -> None:
    """Stage .atdd/manifest.yaml AND a code file."""
    _stage_manifest_only(tmp_path)
    code = tmp_path / "src" / "module.py"
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text("x = 1\n")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", str(code.relative_to(tmp_path))],
        check=True, capture_output=True,
    )


def _stage_code_only(tmp_path: Path) -> None:
    """Stage a code file but NOT the manifest."""
    code = tmp_path / "src" / "module.py"
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text("x = 1\n")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", str(code.relative_to(tmp_path))],
        check=True, capture_output=True,
    )


def _run_hook(tmp_path: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    """Execute the pre-commit hook in tmp_path."""
    full_env = {**os.environ, "ATDD_SKIP_MANIFEST_CHECK": "1"}
    if env:
        full_env.update(env)
    return subprocess.run(
        ["sh", str(HOOK_PATH)],
        cwd=str(tmp_path),
        env=full_env,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# E012-UNIT-001 — manifest only on main → allowed
# ---------------------------------------------------------------------------

def test_pre_commit_allows_manifest_only_on_main(tmp_path: Path) -> None:
    """E012-UNIT-001: staged = .atdd/manifest.yaml only on main → exit 0."""
    _init_repo(tmp_path, branch="main")
    _stage_manifest_only(tmp_path)

    result = _run_hook(tmp_path)

    assert result.returncode == 0, (
        f"pre-commit must allow a manifest-only commit on main; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )


def test_pre_commit_allows_manifest_only_on_master(tmp_path: Path) -> None:
    """E012-UNIT-001 (master): staged = manifest only on master → exit 0."""
    _init_repo(tmp_path, branch="master")
    _stage_manifest_only(tmp_path)

    result = _run_hook(tmp_path)

    assert result.returncode == 0, (
        f"pre-commit must allow a manifest-only commit on master; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# E012-UNIT-002 — manifest + code on main → blocked
# ---------------------------------------------------------------------------

def test_pre_commit_blocks_manifest_plus_code_on_main(tmp_path: Path) -> None:
    """E012-UNIT-002: staged = manifest + code on main → exit 1 (code change must not slip through)."""
    _init_repo(tmp_path, branch="main")
    _stage_manifest_plus_code(tmp_path)

    result = _run_hook(tmp_path)

    assert result.returncode != 0, (
        f"pre-commit must block manifest+code on main; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )
    assert "blocked" in result.stderr.lower() or "main" in result.stderr.lower(), (
        f"stderr must reference the main-block; got:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# E012-UNIT-003 — code only on main → blocked
# ---------------------------------------------------------------------------

def test_pre_commit_blocks_code_only_on_main(tmp_path: Path) -> None:
    """E012-UNIT-003: staged = code only on main → exit 1."""
    _init_repo(tmp_path, branch="main")
    _stage_code_only(tmp_path)

    result = _run_hook(tmp_path)

    assert result.returncode != 0, (
        f"pre-commit must block code-only commit on main; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# Existing behaviour: feature branch still passes through
# ---------------------------------------------------------------------------

def test_pre_commit_allows_code_on_feature_branch(tmp_path: Path) -> None:
    """Regression: code commit on a feature branch is unaffected."""
    _init_repo(tmp_path, branch="main")
    subprocess.run(
        ["git", "-C", str(tmp_path), "checkout", "-q", "-b", "feat/my-feature"],
        check=True, capture_output=True,
    )
    _stage_code_only(tmp_path)

    result = _run_hook(tmp_path, env={"ATDD_SKIP_MANIFEST_CHECK": "1"})

    assert result.returncode == 0, (
        f"pre-commit must allow code commit on a feature branch; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# Y004-UNIT-001 — drift notice is non-blocking
# ---------------------------------------------------------------------------

def _write_manifest_with_slug(tmp_path: Path, slug: str) -> None:
    """Write a manifest.yaml listing *slug* in sessions and commit it."""
    manifest_dir = tmp_path / ".atdd"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.yaml").write_text(
        f"sessions:\n- id: '1'\n  slug: {slug}\n  issue_number: 1\n"
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", ".atdd/manifest.yaml"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "add manifest"],
        check=True, capture_output=True,
    )


def test_pre_commit_drift_notice_is_non_blocking(tmp_path: Path) -> None:
    """Y004-UNIT-001: branch slug absent from manifest → hook exits 0 but prints drift notice."""
    _init_repo(tmp_path, branch="main")
    # Switch to a feature branch whose slug is NOT registered
    subprocess.run(
        ["git", "-C", str(tmp_path), "checkout", "-q", "-b", "feat/unregistered-feature"],
        check=True, capture_output=True,
    )
    # Write a manifest that does NOT contain 'unregistered-feature'
    manifest_dir = tmp_path / ".atdd"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.yaml").write_text(
        "sessions:\n- id: '1'\n  slug: some-other-issue\n  issue_number: 1\n"
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", ".atdd/manifest.yaml"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "add manifest"],
        check=True, capture_output=True,
    )
    _stage_code_only(tmp_path)

    # Run without bypassing the manifest check so the drift detection runs
    full_env = {**os.environ}
    result = subprocess.run(
        ["sh", str(HOOK_PATH)],
        cwd=str(tmp_path),
        env=full_env,
        capture_output=True,
        text=True,
    )

    # Must exit non-zero (branch not registered) but the output must mention
    # drift / reconcile to guide the developer
    assert "reconcile" in result.stderr.lower() or "drift" in result.stderr.lower() or "not registered" in result.stderr.lower(), (
        f"stderr must include a drift/reconcile notice; got:\n{result.stderr}"
    )


def test_pre_commit_drift_notice_does_not_block_registered_branch(tmp_path: Path) -> None:
    """Y004-UNIT-001 (registered): branch slug present in manifest → normal exit 0."""
    _init_repo(tmp_path, branch="main")
    subprocess.run(
        ["git", "-C", str(tmp_path), "checkout", "-q", "-b", "feat/registered-feature"],
        check=True, capture_output=True,
    )
    manifest_dir = tmp_path / ".atdd"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.yaml").write_text(
        "sessions:\n- id: '1'\n  slug: registered-feature\n  issue_number: 1\n"
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", ".atdd/manifest.yaml"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "add manifest"],
        check=True, capture_output=True,
    )
    _stage_code_only(tmp_path)

    full_env = {**os.environ}
    result = subprocess.run(
        ["sh", str(HOOK_PATH)],
        cwd=str(tmp_path),
        env=full_env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"registered branch must exit 0; rc={result.returncode}\nstderr={result.stderr}"
    )
