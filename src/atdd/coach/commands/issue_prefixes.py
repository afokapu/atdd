"""Neutral home for the issue-type → commit/branch prefix constants.

EXTRACTED from ``issue.py`` (the ``atdd issue`` monolith) by C5a (#1382, umbrella
#1303) so ``branch.py`` / ``pr.py`` — and any other consumer — stop hard-depending
on the monolith for these two constants. ``issue.py`` re-exports them unchanged
(single source of truth stays here), so nothing breaks now and C5b (#1309) can
delete the ``atdd issue`` subparser + monolith without taking the prefixes with it.

Contains NO logic — just the two data constants that were previously defined in
``issue.py``.
"""
from __future__ import annotations

# Issue type → conventional commit / branch prefix mapping.
# Used by `atdd new` (title prefix) and `atdd branch` (worktree prefix).
TYPE_TO_PREFIX = {
    "implementation": "feat",
    "migration": "feat",
    "refactor": "refactor",
    "analysis": "chore",
    "planning": "chore",
    "cleanup": "chore",
    "tracking": "chore",
}

# Allowed branch prefixes (derived from TYPE_TO_PREFIX values + fix, docs, devops).
ALLOWED_BRANCH_PREFIXES = ("feat", "fix", "refactor", "chore", "docs", "devops")
