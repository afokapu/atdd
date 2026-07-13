# URN: test:integration-hardening:coach-single-command-driver:classifier-matches-argv-not-substrings
# Issue: #1454 (wire the PreToolUse prohibition guard)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""The classifier must match ARGV, not raw substrings (#1454, latent from #668).

While the PreToolUse hook was dead code a substring matcher was harmless.  Now
that the guard is live, ``"gh issue create" in command`` blocks any command that
merely *mentions* the forbidden string — a ``grep`` for it, a commit message
warning against it, a doc quoting it.  A guard whose first act is to block
someone's ``grep`` trains people to disable it: the exact failure mode the guard
exists to prevent.

The fix is argv-awareness.  ``shlex.split`` collapses a *quoted* mention into a
single token while a real invocation yields consecutive tokens:

    'gh issue create --title x'          -> ['gh', 'issue', 'create', ...]   BLOCK
    'grep -rn "gh issue create" docs/'   -> ['grep', '-rn', 'gh issue create', ...]   ALLOW

So the registry declares ``argv: [gh, issue, create]`` and the matcher scans for
that *consecutive token run*.  Scanning the whole token list (rather than only
the head) keeps real invocations blocked when they are not bare-prefixed:
``&&``/``;`` chains and leading env assignments both survive tokenization as
separate tokens.

Fail-open (Decision 6, #668) is preserved: an unbalanced quote makes
``shlex.split`` raise, and the classifier must allow rather than let the
exception escape and brick the agent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.forbidden_command_classifier import Decision, classify


def _classify(command: str, tmp_path: Path) -> Decision:
    return classify(command, tool="Bash", repo_root=tmp_path)


# ---------------------------------------------------------------------------
# Real invocations stay blocked (regression guard on the fix)
# ---------------------------------------------------------------------------

def test_1_gh_issue_create_is_blocked(tmp_path: Path) -> None:
    d = _classify("gh issue create --title x", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-GH-ISSUE-CREATE"


def test_4_gh_pr_create_is_blocked(tmp_path: Path) -> None:
    d = _classify("gh pr create", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-GH-PR-CREATE"


def test_9_leading_env_assignment_still_blocks(tmp_path: Path) -> None:
    """A leading env assignment must not smuggle the invocation past the guard."""
    d = _classify("GH_TOKEN=x gh issue create", tmp_path)
    assert d.action == "block"
    assert d.rule_id == "ATDD-FORBID-GH-ISSUE-CREATE"


@pytest.mark.parametrize("cmd", [
    "command -v gh; gh issue create --title x",
    "git fetch && gh pr create --base main",
    "cd /tmp; gh issue create --title x --body y",
])
def test_9b_non_bare_prefixed_invocations_still_block(tmp_path: Path, cmd: str) -> None:
    """Chained invocations are still real invocations — the token scan must find them."""
    d = _classify(cmd, tmp_path)
    assert d.action == "block", f"chained invocation slipped through: {cmd!r}"


# ---------------------------------------------------------------------------
# Mere MENTIONS of a forbidden command are not invocations — these are the bug
# ---------------------------------------------------------------------------

def test_2_grep_for_the_forbidden_string_is_allowed(tmp_path: Path) -> None:
    d = _classify('grep -rn "gh issue create" docs/', tmp_path)
    assert d.action == "allow", "searching for the string is not running the command"


def test_3_commit_message_mentioning_the_forbidden_string_is_allowed(tmp_path: Path) -> None:
    d = _classify('git commit -m "docs: never use gh issue create"', tmp_path)
    assert d.action == "allow", "warning against the command is not running it"


def test_6_echo_of_the_forbidden_string_is_allowed(tmp_path: Path) -> None:
    d = _classify('echo "gh issue create"', tmp_path)
    assert d.action == "allow", "printing the string is not running the command"


# ---------------------------------------------------------------------------
# True negatives that must stay negative
# ---------------------------------------------------------------------------

def test_5_atdd_native_replacement_is_allowed(tmp_path: Path) -> None:
    d = _classify("atdd author issue --title x --slug y", tmp_path)
    assert d.action == "allow"


def test_7_gh_issue_list_is_allowed(tmp_path: Path) -> None:
    """`list` is not a prohibited verb — only `create` is."""
    d = _classify("gh issue list", tmp_path)
    assert d.action == "allow"


# ---------------------------------------------------------------------------
# Fail open (Decision 6, #668): a tokenizer error must never brick the agent
# ---------------------------------------------------------------------------

def test_8_unbalanced_quote_fails_open(tmp_path: Path) -> None:
    d = _classify('echo "oops', tmp_path)  # shlex.split raises on this
    assert d.action == "allow", "a tokenizer error must fail OPEN, not block"
