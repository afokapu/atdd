# URN: test:integration-hardening:coach-single-command-driver:E006-UNIT-classifier-corpus
# Acceptance: acc:integration-hardening:E006-UNIT-001-classifier-blocks-gh-issue-create
# Acceptance: acc:integration-hardening:E006-UNIT-002-classifier-blocks-gh-pr-create
# Acceptance: acc:integration-hardening:E006-UNIT-003-classifier-blocks-cmux-send-claude
# Acceptance: acc:integration-hardening:E006-UNIT-004-classifier-blocks-git-config-bare-unscoped
# Acceptance: acc:integration-hardening:E006-UNIT-005-classifier-allows-git-config-worktree-scoped
# Acceptance: acc:integration-hardening:E006-UNIT-006-classifier-allows-gh-pr-view-oneoff
# Acceptance: acc:integration-hardening:E006-UNIT-007-classifier-blocks-loop-construct
# Acceptance: acc:integration-hardening:E006-UNIT-008-every-decision-written-to-audit-log
# WMBT: wmbt:integration-hardening:E006
# Phase: RED
# Layer: domain
"""Classifier corpus tests — true-positive and true-negative for each forbidden pattern."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.utils.forbidden_command_classifier import Decision, classify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify(command: str, tmp_path: Path) -> Decision:
    """Classify *command* in isolation using *tmp_path* as repo root."""
    return classify(command, tool="Bash", repo_root=tmp_path)


# ---------------------------------------------------------------------------
# AC-UNIT-001: gh issue create → hard block
# ---------------------------------------------------------------------------

def test_gh_issue_create_is_blocked(tmp_path: Path) -> None:
    d = _classify("gh issue create test-slug", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-GH-ISSUE-CREATE"
    assert d.alternative is not None and "atdd issue" in d.alternative


def test_gh_issue_create_with_flags_is_blocked(tmp_path: Path) -> None:
    d = _classify("gh issue create --title 'foo' --body 'bar'", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-GH-ISSUE-CREATE"


# True negative: gh issue list is NOT blocked
def test_gh_issue_list_is_allowed(tmp_path: Path) -> None:
    d = _classify("gh issue list", tmp_path)
    assert d.action == "allow"


# ---------------------------------------------------------------------------
# AC-UNIT-002: gh pr create → hard block
# ---------------------------------------------------------------------------

def test_gh_pr_create_is_blocked(tmp_path: Path) -> None:
    d = _classify("gh pr create --title x --body y", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-GH-PR-CREATE"
    assert d.alternative is not None and "atdd pr" in d.alternative


def test_gh_pr_create_bare_is_blocked(tmp_path: Path) -> None:
    d = _classify("gh pr create", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-GH-PR-CREATE"


# True negative: gh pr merge is NOT blocked by this rule
def test_gh_pr_merge_is_not_blocked_by_pr_create_rule(tmp_path: Path) -> None:
    d = _classify("gh pr merge 660 --squash", tmp_path)
    assert d.action == "allow" or (d.rule_id != "ATDD-FORBID-GH-PR-CREATE")


# ---------------------------------------------------------------------------
# AC-UNIT-003: cmux send with "claude " → hard block
# ---------------------------------------------------------------------------

def test_cmux_send_claude_is_blocked(tmp_path: Path) -> None:
    d = _classify('cmux send surface:1 "claude -p hello"', tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-CMUX-SEND-CLAUDE"
    assert d.alternative is not None and "atdd spawn" in d.alternative


def test_cmux_send_claude_with_resume_is_blocked(tmp_path: Path) -> None:
    d = _classify("cmux send surface:355 claude --resume abc123", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-CMUX-SEND-CLAUDE"


# True negative: cmux send without "claude " payload is NOT blocked
def test_cmux_send_other_payload_is_allowed(tmp_path: Path) -> None:
    d = _classify("cmux send surface:1 ls", tmp_path)
    assert d.action == "allow"


# True negative: cmux new-surface is NOT blocked
def test_cmux_new_surface_is_allowed(tmp_path: Path) -> None:
    d = _classify("cmux new-surface --worktree ./feat-x", tmp_path)
    assert d.action == "allow"


# ---------------------------------------------------------------------------
# AC-UNIT-004: git config core.bare without --worktree → hard block
# ---------------------------------------------------------------------------

def test_git_config_core_bare_is_blocked(tmp_path: Path) -> None:
    d = _classify("git config core.bare true", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-GIT-CONFIG-BARE-UNSCOPED"
    assert d.alternative is not None and "--worktree" in d.alternative


def test_git_config_core_worktree_is_blocked(tmp_path: Path) -> None:
    d = _classify("git config core.worktree /some/path", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-GIT-CONFIG-BARE-UNSCOPED"


def test_git_C_flag_config_core_bare_is_blocked(tmp_path: Path) -> None:
    d = _classify("git -C /some/path config core.bare true", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-GIT-CONFIG-BARE-UNSCOPED"


# ---------------------------------------------------------------------------
# AC-UNIT-005: git config --worktree core.bare → allowed (true negative)
# ---------------------------------------------------------------------------

def test_git_config_worktree_scoped_bare_is_allowed(tmp_path: Path) -> None:
    d = _classify("git config --worktree core.bare true", tmp_path)
    assert d.action == "allow"


def test_git_config_worktree_scoped_core_worktree_is_allowed(tmp_path: Path) -> None:
    d = _classify("git config --worktree core.worktree /path", tmp_path)
    assert d.action == "allow"


# ---------------------------------------------------------------------------
# AC-UNIT-006: gh pr view one-off → loop block allows on first call
# ---------------------------------------------------------------------------

def test_gh_pr_view_oneoff_is_allowed(tmp_path: Path) -> None:
    d = _classify("gh pr view 660", tmp_path)
    assert d.action == "allow"


def test_gh_pr_list_oneoff_is_allowed(tmp_path: Path) -> None:
    d = _classify("gh pr list", tmp_path)
    assert d.action == "allow"


def test_gh_pr_checks_oneoff_is_allowed(tmp_path: Path) -> None:
    d = _classify("gh pr checks 660", tmp_path)
    assert d.action == "allow"


# ---------------------------------------------------------------------------
# AC-UNIT-007: loop construct → immediate block regardless of call count
# ---------------------------------------------------------------------------

def test_while_loop_gh_pr_list_is_blocked(tmp_path: Path) -> None:
    d = _classify("while true; do gh pr list; done", tmp_path)
    assert d.action == "block"
    assert d.rule_id is not None and "LOOP" in d.rule_id


def test_until_loop_gh_pr_view_is_blocked(tmp_path: Path) -> None:
    d = _classify("until false; do gh pr view 660; done", tmp_path)
    assert d.action == "block"


def test_for_loop_gh_pr_checks_is_blocked(tmp_path: Path) -> None:
    d = _classify("for i in 1 2 3; do gh pr checks 660; done", tmp_path)
    assert d.action == "block"


# Loop construct detection fires even on the first call (no prior state needed)
def test_loop_block_fires_without_prior_state(tmp_path: Path) -> None:
    state_file = tmp_path / ".atdd" / "runtime" / "tool_use_counts.json"
    assert not state_file.exists()
    d = _classify("while true; do gh pr list; done", tmp_path)
    assert d.action == "block"


# Frequency-based: second call within TTL blocks
def test_gh_pr_list_second_call_is_blocked(tmp_path: Path) -> None:
    _classify("gh pr list", tmp_path)  # first call → allow
    d = _classify("gh pr list", tmp_path)  # second call → block
    assert d.action == "block"
    assert d.rule_id is not None and "LOOP" in d.rule_id


# ---------------------------------------------------------------------------
# AC-UNIT-008: audit log written for every decision
# ---------------------------------------------------------------------------

def test_audit_log_written_on_block(tmp_path: Path) -> None:
    _classify("gh issue create foo", tmp_path)
    audit = tmp_path / ".atdd" / "runtime" / "tool_use_audit.jsonl"
    assert audit.exists(), "audit log must be created after classify()"
    record = json.loads(audit.read_text().strip().splitlines()[-1])
    assert record["decision"] == "block"
    assert record["tool"] == "Bash"
    assert "command" in record
    assert "ts" in record
    assert "rule_id" in record
    assert "reason" in record
    assert "alternative" in record


def test_audit_log_written_on_allow(tmp_path: Path) -> None:
    _classify("git status", tmp_path)
    audit = tmp_path / ".atdd" / "runtime" / "tool_use_audit.jsonl"
    assert audit.exists()
    record = json.loads(audit.read_text().strip().splitlines()[-1])
    assert record["decision"] == "allow"


def test_audit_log_appends_multiple_records(tmp_path: Path) -> None:
    _classify("gh issue create a", tmp_path)
    _classify("gh pr create --title b", tmp_path)
    _classify("git status", tmp_path)
    audit = tmp_path / ".atdd" / "runtime" / "tool_use_audit.jsonl"
    lines = audit.read_text().strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        json.loads(line)  # Each line must be valid JSON


# ---------------------------------------------------------------------------
# Safe commands — safe commands must not be blocked
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "git status",
    "git log --oneline -10",
    "git diff --name-only",
    "git add src/foo.py",
    "git commit -m 'feat: x'",
    "atdd validate",
    "atdd issue open",
    "atdd pr 668",
    "pytest src/atdd/coach/utils/tests/ -x",
    "ls -la",
    "cat pyproject.toml",
])
def test_safe_commands_are_allowed(tmp_path: Path, cmd: str) -> None:
    d = _classify(cmd, tmp_path)
    assert d.action == "allow", f"safe command incorrectly blocked: {cmd!r}"
