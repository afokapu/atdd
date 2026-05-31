# URN: component:govern-lifecycle:agnostic-git-config-bare-guard-via-path-shim:core_bare_baseline:backend:application
# Runtime: python
# Purpose: Detect a poisoned shared .git/config (core.bare=true) for the CI validator.
"""Shared core.bare baseline check (issue #884).

Defense-in-depth detection layer that complements the agent-agnostic
``.atdd/bin/git`` PATH shim (the prevention layer). When the effective
``git config --get core.bare`` is ``true`` the repository's shared .git/config
has been poisoned — every linked worktree then reports
"fatal: this operation must be run in a work tree". This module exposes a pure
check the coach validator (and ``atdd validate``) runs to fail on such a
baseline regardless of which agent wrote it.

A worktree-scoped ``core.bare=false`` override makes the *effective* value
false, so checking the effective value naturally honours per-worktree repairs.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List

_log = logging.getLogger(__name__)


def effective_core_bare(repo_dir: Path) -> str:
    """Return the effective ``git config --get core.bare`` value, lowercased.

    Returns "" when the key is unset or git cannot be run (best-effort: a repo
    we cannot inspect is treated as not-poisoned so the check never false-reds).
    """
    try:
        result = subprocess.run(
            ["git", "config", "--get", "core.bare"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        _log.warning(
            "core_bare_baseline: could not read core.bare",
            extra={"error": str(exc), "error_type": type(exc).__name__, "repo": str(repo_dir)},
        )
        return ""
    return result.stdout.strip().lower()


def check_core_bare_not_poisoned(repo_dir: Path) -> List[str]:
    """Return a list of violation messages; empty when the baseline is clean.

    A single violation is reported when the effective core.bare is ``true``,
    naming the worktree-scoped repair so an operator never has to hand-edit
    .git/config.
    """
    if effective_core_bare(repo_dir) == "true":
        return [
            f"shared .git/config in {repo_dir} has core.bare=true (poisoned) — "
            "every worktree will report 'fatal: this operation must be run in a "
            "work tree'. Repair: git config --worktree core.bare false"
        ]
    return []
