# URN: test:mediate-worker-decisions:mediate-decision:C002-UNIT-002-unrecognized-destructive-human-required
# Acceptance: acc:mediate-worker-decisions:C002-UNIT-002-unrecognized-destructive-human-required
# WMBT: wmbt:mediate-worker-decisions:C002
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C002-UNIT-002 — destructive ops BEYOND the original denylist escalate.

The original C002-UNIT-001 only feeds the matcher strings that are already
denylist members, so it can never catch denylist *incompleteness*. This test is
adversarial: it asserts ``human_required`` for work-destroying git/fs/db
operations that are NOT substrings of the original
``("git push", "git merge", "gh pr merge", "rm -rf", "drop table",
"force push", "destructive migration", "force-push")`` denylist, and keeps the
read-only commands classifying ``auto``. It must FAIL against the current
denylist (which returns ``safe`` for, e.g., ``git reset --hard``).
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.mediate_decision.src.domain.safety_classifier import (
    classify,
)

# Destructive operations absent from the original substring denylist. Each one
# discards work, deletes refs/files, or mutates a datastore irreversibly.
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

READ_ONLY_SAFE = ["git status", "ls -la", "pytest -q"]


@pytest.mark.parametrize("command", DESTRUCTIVE_NOT_IN_OLD_DENYLIST)
def test_unrecognized_destructive_option_is_human_required(command):
    sc = classify("Proceed?", [command, "do nothing"])
    assert not sc.is_safe, f"{command!r} must escalate to a human, not auto-apply"
    assert sc.matched_rule is not None


@pytest.mark.parametrize("command", READ_ONLY_SAFE)
def test_read_only_option_is_auto(command):
    sc = classify("Proceed?", [command, "do nothing"])
    assert sc.is_safe, f"{command!r} is read-only and should classify auto"
