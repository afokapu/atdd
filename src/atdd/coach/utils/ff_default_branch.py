"""Fast-forward the local default-branch worktree after a PR merge.

This module provides :func:`fast_forward_default_branch`, which locates the
local worktree whose branch matches ``<default_branch>``, checks whether its
tracked files are clean, and runs ``git merge --ff-only origin/<default_branch>``
when it is safe to do so.

Rationale (issue #770): ``gh pr merge`` advances ``origin/main`` server-side
but never updates the local ``main`` worktree.  Every subsequent branch is cut
from the stale local ref, compounding drift across sessions.

Safety guarantees:
  - Fast-forward only: never creates a merge commit or rebases.
  - Skips silently with a printed notice when tracked files are modified.
  - Untracked files alone do not block the fast-forward.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_default_branch_worktree(repo_root: Path, default_branch: str) -> Path | None:
    """Return the path of the worktree whose HEAD branch is ``default_branch``.

    Uses ``git worktree list --porcelain`` to enumerate all worktrees.
    Returns None when no match is found or the command fails.
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=10,
            cwd=repo_root,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning(
            "git worktree list failed: %s",
            exc,
            extra={"error": str(exc), "repo_root": str(repo_root)},
        )
        return None

    if result.returncode != 0:
        logger.warning(
            "git worktree list exited %d: %s",
            result.returncode, result.stderr.strip(),
            extra={"returncode": result.returncode},
        )
        return None

    current_path: str | None = None
    target_ref = f"refs/heads/{default_branch}"

    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("worktree "):
            current_path = line[len("worktree "):].strip()
        elif line.startswith("branch ") and current_path is not None:
            branch_ref = line[len("branch "):].strip()
            if branch_ref == target_ref:
                return Path(current_path)

    return None


def fast_forward_default_branch(repo_root: Path, default_branch: str) -> None:
    """Fast-forward the local default-branch worktree to ``origin/<default_branch>``.

    Steps:
      1. Fetch ``origin/<default_branch>`` to update the remote-tracking ref.
      2. Locate the local worktree whose branch is ``<default_branch>``.
      3. Check whether its tracked files are clean (``git diff --quiet HEAD``).
         - If clean: run ``git merge --ff-only origin/<default_branch>``.
         - If dirty: print a notice and return without touching the tree.

    Args:
        repo_root: Path to any worktree in the repository (used for git context).
        default_branch: Name of the default branch (e.g. ``"main"``).
    """
    # Step 1: targeted fetch
    try:
        subprocess.run(
            ["git", "fetch", "origin", default_branch],
            capture_output=True, text=True, timeout=30,
            cwd=repo_root,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning(
            "git fetch origin %s failed: %s",
            default_branch, exc,
            extra={"default_branch": default_branch, "error": str(exc)},
        )
        return

    # Step 2: locate the default-branch worktree
    wt_path = _find_default_branch_worktree(repo_root, default_branch)
    if wt_path is None:
        logger.info(
            "No local worktree found for branch '%s'; skipping fast-forward.",
            default_branch,
            extra={"default_branch": default_branch},
        )
        return

    # Step 3a: check dirty state (tracked files only; untracked are irrelevant)
    try:
        diff_result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=wt_path,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning(
            "git diff --quiet HEAD failed in %s: %s",
            wt_path, exc,
            extra={"worktree": str(wt_path), "error": str(exc)},
        )
        return

    if diff_result.returncode != 0:
        print(
            f"  Note: Skipping fast-forward of '{default_branch}' worktree — "
            f"modified tracked files detected at {wt_path}. "
            f"Commit or stash your changes, then run: "
            f"git -C {wt_path} merge --ff-only origin/{default_branch}"
        )
        return

    # Step 3b: fast-forward
    try:
        ff_result = subprocess.run(
            ["git", "merge", "--ff-only", f"origin/{default_branch}"],
            capture_output=True, text=True, timeout=30,
            cwd=wt_path,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning(
            "git merge --ff-only failed in %s: %s",
            wt_path, exc,
            extra={"worktree": str(wt_path), "error": str(exc)},
        )
        return

    if ff_result.returncode == 0:
        print(
            f"  Fast-forwarded '{default_branch}' worktree to "
            f"origin/{default_branch} ({wt_path})"
        )
    else:
        logger.warning(
            "git merge --ff-only failed in %s: %s",
            wt_path, ff_result.stderr.strip(),
            extra={"worktree": str(wt_path), "stderr": ff_result.stderr.strip()},
        )
