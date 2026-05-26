# Acceptance: acc:integration-hardening:C002-UNIT-001-pre-push-blocks-bare-mode
# Acceptance: acc:integration-hardening:C002-UNIT-002-pre-push-passes-normal
"""Unit tests for the pre-push bare-mode contamination guard (#629 Layer 1).

Background: PRs #625 and #627 each pushed 220,000-line deletions because
their worktrees had ``core.bare=true`` set by a polluting validator test
(#619). The fix landed in #622 but did not catch every polluting path —
on 2026-05-12 the main worktree itself was discovered with the same
flag set. This hook is the runtime last-line-of-defense.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src/atdd/coach/templates/hooks/pre-push"

# Standard stdin payload (local_ref local_sha remote_ref remote_sha)
PUSH_STDIN = (
    "refs/heads/feat/x 0000000000000000000000000000000000000000 "
    "refs/heads/feat/x 1111111111111111111111111111111111111111\n"
)


def _init_repo(tmp_path: Path) -> None:
    """Initialize a fresh, non-bare git repo inside tmp_path.

    Test hygiene (#619/#622 contamination class): every git command takes
    explicit ``-C str(tmp_path)``; we never inherit cwd or operate on the
    invoking process's repo.
    """
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True,
        capture_output=True,
    )


def _run_hook(tmp_path: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    """Execute the pre-push hook with the standard stdin payload.

    ``CI=true`` + ``ATDD_SKIP_VERSION_GATE=1`` bypass the unrelated version
    gate so the test focuses on the bare-mode check.
    """
    full_env = {
        **os.environ,
        "CI": "true",
        "ATDD_SKIP_VERSION_GATE": "1",
    }
    if env:
        full_env.update(env)
    return subprocess.run(
        ["sh", str(HOOK_PATH), "origin", "https://example.invalid/x.git"],
        cwd=str(tmp_path),
        input=PUSH_STDIN,
        env=full_env,
        capture_output=True,
        text=True,
    )


def test_pre_push_blocks_when_core_bare_true(tmp_path: Path) -> None:
    """C002-UNIT-001: core.bare=true must block the push."""
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "core.bare", "true"],
        check=True,
        capture_output=True,
    )

    result = _run_hook(tmp_path)

    assert result.returncode != 0, (
        f"pre-push must exit non-zero when core.bare=true; "
        f"got rc={result.returncode}\nstderr={result.stderr}"
    )
    assert "bare" in result.stderr.lower() or "core.bare" in result.stderr.lower(), (
        f"stderr must reference bare-mode contamination; got:\n{result.stderr}"
    )


def test_pre_push_skip_env_overrides_bare_block(tmp_path: Path) -> None:
    """C002-UNIT-001 (E030 regression): ATDD_SKIP_BARE_CHECK=1 is retired; hook blocks regardless."""
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "core.bare", "true"],
        check=True,
        capture_output=True,
    )

    result = _run_hook(tmp_path, env={"ATDD_SKIP_BARE_CHECK": "1"})

    # E030 (2026-05-26): ATDD_SKIP_BARE_CHECK retired unconditionally.
    # The env var is ignored; the bare-mode gate must still fire.
    assert result.returncode != 0, (
        f"ATDD_SKIP_BARE_CHECK=1 must be ignored (E030); hook must still block; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )
    assert "core.bare" in result.stderr, (
        f"bare-mode error must still appear when env var is set; got:\n{result.stderr}"
    )


def test_pre_push_passes_normal_worktree(tmp_path: Path) -> None:
    """C002-UNIT-002: a non-bare worktree is not blocked by the bare-mode check."""
    _init_repo(tmp_path)
    # core.bare defaults to false; we explicitly assert that for documentation.
    cfg = subprocess.run(
        ["git", "-C", str(tmp_path), "config", "--get", "core.bare"],
        capture_output=True,
        text=True,
    )
    assert cfg.stdout.strip() in ("false", ""), (
        f"expected core.bare=false/unset in a fresh repo; got {cfg.stdout!r}"
    )

    result = _run_hook(tmp_path)

    # The bare-mode check specifically must not fire. The hook can still exit
    # non-zero for unrelated reasons (the existing main-block check fires when
    # pushing to refs/heads/main — but the stdin payload here targets feat/x).
    bare_strings = ("core.bare=true", "bare-mode")
    matched = [s for s in bare_strings if s in result.stderr]
    assert not matched, (
        f"bare-mode error must not fire on a normal worktree; matched: {matched}\n"
        f"stderr: {result.stderr}"
    )
