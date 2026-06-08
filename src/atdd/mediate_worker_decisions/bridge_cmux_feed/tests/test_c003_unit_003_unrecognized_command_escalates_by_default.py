# URN: test:mediate-worker-decisions:bridge-cmux-feed:C003-UNIT-003-unrecognized-command-escalates-by-default
# Acceptance: acc:mediate-worker-decisions:C003-UNIT-003-unrecognized-command-escalates-by-default
# WMBT: wmbt:mediate-worker-decisions:C003
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C003-UNIT-003 — the tool_input gate is allowlist-based (escalate-by-default).

The original C003-UNIT-001 only checks one denylist member (``git push``) and
one safe case (``ls -la``), so it cannot catch the real defect: a substring
denylist whose *default* disposition is ``auto`` silently auto-approved
``git reset --hard``, ``git clean -fd`` and ``git branch -D`` in a live stress
test. This adversarial test asserts the safe posture — ``auto`` ONLY for a known
read-only allowlist, and ``human_required`` for every destructive or
unrecognized command. It must FAIL against the current denylist (which returns
``auto`` for, e.g., ``git reset --hard``).
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.tool_input_safety import (
    classify,
)

# Destructive / unrecognized commands absent from the original denylist.
DESTRUCTIVE_NOT_IN_OLD_DENYLIST = [
    "git reset --hard HEAD",
    "git clean -fd build/",
    "git clean -x",
    "git branch -D feature/old",
    "git checkout --force main",
    "git restore .",
    "git stash drop",
    "git stash clear",
    "git rebase main",
    "git update-ref -d refs/heads/topic",
    "git push --delete origin topic",
    "git reflog expire --expire=now --all",
    "DELETE FROM users",
    "TRUNCATE TABLE sessions",
    "dd if=/dev/zero of=/dev/sda",
    "mkfs.ext4 /dev/sdb1",
    "chmod -R 777 /",
    "truncate -s 0 important.log",
]

# Known-safe read-only commands — these stay auto so the autonomous coach keeps
# unblocking the common read/inspect prompts.
READ_ONLY_SAFE = [
    "git status",
    "git log --oneline",
    "git diff HEAD~1",
    "ls -la",
    "cat README.md",
    "grep -rn TODO src",
    "rg pattern",
    "echo hello",
    "pwd",
    "pytest -q",
    "atdd validate",
    "atdd gate",
]


@pytest.mark.parametrize("command", DESTRUCTIVE_NOT_IN_OLD_DENYLIST)
def test_unrecognized_command_is_human_required(command):
    assert classify(command) == "human_required", (
        f"{command!r} is destructive/unrecognized and must escalate, not auto-approve"
    )


@pytest.mark.parametrize("command", READ_ONLY_SAFE)
def test_read_only_command_is_auto(command):
    assert classify(command) == "auto", f"{command!r} is read-only and should be auto"
