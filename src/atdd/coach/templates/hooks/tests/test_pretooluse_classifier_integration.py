# URN: test:integration-hardening:coach-single-command-driver:E006-INTEGRATION-hook-blocks-forbidden
# Acceptance: acc:integration-hardening:E006-INTEGRATION-001-hook-exits-2-for-gh-issue-create
# Acceptance: acc:integration-hardening:E006-SMOKE-001-hook-blocks-real-claude-invocation-against-installed-classifier
# WMBT: wmbt:integration-hardening:E006
# Phase: GREEN
# Layer: integration
"""Integration tests for the claude-pre-tool-use hook + classifier (issue #668).

These tests invoke the hook script via subprocess with a simulated Claude Code
JSON payload on stdin and verify:
  - Exit code 2 for hard-block commands (educational error on stderr).
  - Exit code 0 for safe / one-off commands.
  - ATDD_REPO_ROOT env var correctly points the hook at the real classifier.

The hook runs in a temporary git repo (so ``git rev-parse --show-toplevel``
resolves) while ATDD_REPO_ROOT is set to the actual repo root so the
classifier module and convention YAML are found without copying them.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src/atdd/coach/templates/hooks/claude-pre-tool-use.sh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_tmp_repo(path: Path) -> None:
    """Initialise a minimal git repo at *path* (for git rev-parse to work)."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(path)],
        check=True,
        capture_output=True,
    )
    for key, val in (("user.email", "test@atdd.test"), ("user.name", "atdd test")):
        subprocess.run(
            ["git", "-C", str(path), "config", key, val],
            check=True,
            capture_output=True,
        )


def _bash_payload(command: str) -> bytes:
    """Return the Claude Code JSON payload bytes for a Bash tool call."""
    return json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": ""},
    }).encode()


def _run_hook(
    tmp_path: Path,
    payload: bytes,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run the hook script inside *tmp_path* with *payload* on stdin.

    ATDD_REPO_ROOT is always set to the real REPO_ROOT so the classifier and
    convention YAML are found.  Additional env overrides can be passed via
    *extra_env*.
    """
    env = {
        **os.environ,
        "ATDD_REPO_ROOT": str(REPO_ROOT),
        "ATDD_SKIP_PREPUSH_VALIDATE": "1",  # keep tests fast
        "CI": "false",
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["sh", str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        cwd=str(tmp_path),
        env=env,
    )


# ---------------------------------------------------------------------------
# AC-INTEGRATION-001: gh issue create → exit 2, stderr names atdd issue
# ---------------------------------------------------------------------------


def test_hook_blocks_gh_issue_create(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    result = _run_hook(tmp_path, _bash_payload("gh issue create test"))
    assert result.returncode == 2, f"expected exit 2, got {result.returncode}\nstderr: {result.stderr.decode()}"
    stderr = result.stderr.decode()
    assert "ATDD-FORBID-GH-ISSUE-CREATE" in stderr, f"rule_id missing from stderr: {stderr!r}"
    assert "atdd issue" in stderr, f"alternative missing from stderr: {stderr!r}"


def test_hook_blocks_gh_pr_create(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    result = _run_hook(tmp_path, _bash_payload("gh pr create --title 'x' --body 'y'"))
    assert result.returncode == 2
    stderr = result.stderr.decode()
    assert "ATDD-FORBID-GH-PR-CREATE" in stderr
    assert "atdd pr" in stderr


def test_hook_blocks_cmux_send_claude(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    result = _run_hook(tmp_path, _bash_payload('cmux send surface:1 "claude -p hello"'))
    assert result.returncode == 2
    stderr = result.stderr.decode()
    assert "ATDD-FORBID-CMUX-SEND-CLAUDE" in stderr
    assert "atdd spawn" in stderr


def test_hook_blocks_git_config_core_bare_unscoped(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    result = _run_hook(tmp_path, _bash_payload("git config core.bare true"))
    assert result.returncode == 2
    stderr = result.stderr.decode()
    assert "ATDD-FORBID-GIT-CONFIG-BARE-UNSCOPED" in stderr
    assert "--worktree" in stderr


def test_hook_blocks_while_loop_gh_pr_list(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    result = _run_hook(tmp_path, _bash_payload("while true; do gh pr list; done"))
    assert result.returncode == 2
    assert "LOOP" in result.stderr.decode()


# ---------------------------------------------------------------------------
# Allowed commands — hook must exit 0 and not block safe tool calls
# ---------------------------------------------------------------------------


def test_hook_allows_git_status(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    result = _run_hook(tmp_path, _bash_payload("git status"))
    assert result.returncode == 0, f"git status incorrectly blocked: {result.stderr.decode()}"


def test_hook_allows_gh_pr_view_oneoff(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    result = _run_hook(tmp_path, _bash_payload("gh pr view 660"))
    assert result.returncode == 0, f"gh pr view one-off incorrectly blocked: {result.stderr.decode()}"


def test_hook_allows_git_config_worktree_scoped(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    result = _run_hook(tmp_path, _bash_payload("git config --worktree core.bare true"))
    assert result.returncode == 0, f"--worktree scoped config incorrectly blocked: {result.stderr.decode()}"


def test_hook_allows_atdd_commands(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    result = _run_hook(tmp_path, _bash_payload("atdd validate"))
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Non-Bash tool calls — hook must always allow
# ---------------------------------------------------------------------------


def test_hook_allows_non_bash_tool(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    payload = json.dumps({
        "tool_name": "Read",
        "tool_input": {"file_path": "/some/file.py"},
    }).encode()
    result = _run_hook(tmp_path, payload)
    assert result.returncode == 0


def test_hook_allows_empty_stdin(tmp_path: Path) -> None:
    _init_tmp_repo(tmp_path)
    result = _run_hook(tmp_path, b"")
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Fail-open: classifier absent → hook exits 0
# ---------------------------------------------------------------------------


def test_hook_fails_open_when_classifier_absent(tmp_path: Path) -> None:
    """When ATDD_REPO_ROOT points to a dir with no classifier, hook exits 0."""
    _init_tmp_repo(tmp_path)
    # Point to tmp_path itself — no classifier there
    result = _run_hook(
        tmp_path,
        _bash_payload("gh issue create test"),
        extra_env={"ATDD_REPO_ROOT": str(tmp_path)},
    )
    assert result.returncode == 0, (
        f"hook must fail open when classifier absent, got exit {result.returncode}"
    )
