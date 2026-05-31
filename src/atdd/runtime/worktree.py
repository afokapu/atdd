"""Git worktree creation/removal and branch safety for the ATDD runtime layer.

Coach decomposition Child 5 (docs/coach-decomposition.md §13.5, umbrella #887).

This module is the **single** worktree-creation path. It preserves three
incident defenses from §9 at this layer:

- **I-1** — no bare-directory worktree dispatch. A path that exists but is not a
  valid git working tree (and is not safe-to-clear atdd residue) is refused
  rather than silently dispatched into / overwritten.
- **I-2** — no protected-main commits. Creating a worktree on a protected
  branch (``main`` / ``master``) is refused up front, because an agent
  dispatched there would land commits on protected ``main``
  (2026-05-16 incident).
- **I-9** — ``git config --worktree core.bare false`` on every new worktree.
  This is the canonical fix for the recurring ``core.bare=true`` shared-config
  bleed: the per-worktree override neutralises a contaminated shared config for
  the worktree's lifetime.

Dependency discipline (§3.3): this module imports only stdlib + ``subprocess``
+ ``pathlib``. It MUST NOT import ``atdd.coach.*``, ``atdd.train.*``,
``atdd.integrations.*``, ``atdd.runtime.agent_control`` or
``atdd.runtime.multiplexer``. Callers in the coach layer translate their own
context (issue body, manifest) into the primitive arguments below and route
through this module.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Sequence

_log = logging.getLogger(__name__)

#: Branches an issue worktree must never be created on (I-2). Committing on these
#: from a dispatched agent would land changes on protected ``main``.
DEFAULT_PROTECTED_BRANCHES: tuple[str, ...] = ("main", "master")

#: Entries that mark a path as safe-to-clear atdd residue (pre-fix debris) rather
#: than a foreign directory that must be preserved (I-1).
_ATDD_RESIDUE: frozenset[str] = frozenset({".atdd", ".launch_prompt.txt", ".DS_Store"})


class WorktreeError(Exception):
    """Base class for worktree-layer errors."""


class ProtectedBranchError(WorktreeError):
    """Raised when a worktree would be created on a protected branch (I-2)."""


def is_protected_branch(
    branch: str,
    protected: Sequence[str] = DEFAULT_PROTECTED_BRANCHES,
) -> bool:
    """Return True when ``branch`` is a protected branch (exact match).

    Matching is exact: ``main`` is protected but ``fix/main-thing`` is not.
    """
    return branch.strip() in set(protected)


def assert_safe_branch(
    branch: str,
    protected: Sequence[str] = DEFAULT_PROTECTED_BRANCHES,
) -> None:
    """Raise :class:`ProtectedBranchError` when ``branch`` is protected (I-2)."""
    if is_protected_branch(branch, protected):
        raise ProtectedBranchError(
            f"refusing to create a worktree on protected branch {branch!r}: "
            f"commits from a dispatched agent would land on protected main (I-2)"
        )


def ensure_per_worktree_core_bare_false(
    worktree_path: Path,
    repo_root: Optional[Path] = None,
) -> None:
    """Set ``core.bare=false`` as a per-worktree override on ``worktree_path`` (I-9).

    Enables ``extensions.worktreeConfig`` on the repository first (idempotent;
    required before ``git config --worktree`` writes land in the worktree-local
    ``config.worktree`` file), then writes ``core.bare false`` scoped to this
    worktree only. The ``--worktree`` flag is mandatory for any ``core.*`` write
    so the value never bleeds into the shared config (#884).
    """
    worktree_path = Path(worktree_path)
    config_cwd = Path(repo_root) if repo_root is not None else worktree_path

    try:
        check = subprocess.run(
            ["git", "config", "--get", "extensions.worktreeConfig"],
            cwd=str(config_cwd), capture_output=True, text=True, timeout=10,
        )
        if not (check.returncode == 0 and check.stdout.strip().lower() == "true"):
            subprocess.run(
                ["git", "config", "extensions.worktreeConfig", "true"],
                cwd=str(config_cwd), capture_output=True, text=True, timeout=10,
            )
        subprocess.run(
            ["git", "config", "--worktree", "core.bare", "false"],
            cwd=str(worktree_path), capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        _log.warning(
            "could not set per-worktree core.bare=false",
            extra={"worktree": str(worktree_path), "error": str(exc)},
        )


def _remote_branch_exists(repo_root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "branch", "-r", "--list", f"origin/{branch}"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def ensure_issue_worktree(
    worktree_path: Path,
    branch: str,
    repo_root: Path,
    *,
    issue_number: Optional[int] = None,
    start_point: Optional[str] = None,
    protected_branches: Sequence[str] = DEFAULT_PROTECTED_BRANCHES,
) -> Optional[Path]:
    """Ensure a git worktree for ``branch`` exists at ``worktree_path``.

    Idempotent: an existing git worktree at ``worktree_path`` is returned
    unchanged (with its per-worktree ``core.bare=false`` override re-asserted).

    Incident defenses:

    - **I-2** — raises :class:`ProtectedBranchError` before touching the
      filesystem when ``branch`` is protected.
    - **I-1** — refuses (returns ``None``) when ``worktree_path`` exists with
      foreign content; only an empty directory or atdd residue is cleared.
    - **I-9** — sets ``git config --worktree core.bare false`` on creation.

    Args:
        worktree_path: Absolute target path for the worktree (a flat sibling of
            ``repo_root`` by convention).
        branch: Branch to attach to (existing remote) or create (new ``-b``).
        repo_root: Root of the main checkout the worktree links to.
        issue_number: Optional, for log context only.
        start_point: Optional start ref for a NEW branch (e.g.
            ``origin/main``). Ignored when attaching to an existing remote
            branch.
        protected_branches: Branches treated as protected (I-2).

    Returns:
        The worktree ``Path`` on success, or ``None`` when creation was refused
        or failed (caller surfaces BLOCKED).
    """
    worktree_path = Path(worktree_path)
    repo_root = Path(repo_root)

    # I-2: protected-branch pre-flight, before any filesystem mutation.
    assert_safe_branch(branch, protected_branches)

    # Idempotent: an existing git worktree is reused unchanged.
    if (worktree_path / ".git").exists():
        ensure_per_worktree_core_bare_false(worktree_path, repo_root)
        return worktree_path

    # I-1: triage a path that exists but is not a git worktree. `git worktree
    # add` accepts only a missing or empty directory.
    #   - empty            → git accepts it as-is.
    #   - atdd-only residue → stale debris from the pre-fix bug; safe to clear.
    #   - anything else     → refuse; never silently clobber foreign content.
    if worktree_path.exists():
        entries = {p.name for p in worktree_path.iterdir()}
        if not entries:
            pass  # empty dir
        elif entries <= _ATDD_RESIDUE:
            shutil.rmtree(worktree_path)
        else:
            _log.warning(
                "refusing bare-directory worktree dispatch: path exists and is "
                "not a git worktree",
                extra={
                    "issue": issue_number,
                    "worktree": str(worktree_path),
                },
            )
            return None

    # Attach to an existing remote branch if present, else create a new one.
    if _remote_branch_exists(repo_root, branch):
        add_cmd = [
            "git", "worktree", "add", str(worktree_path), f"origin/{branch}",
        ]
    else:
        add_cmd = ["git", "worktree", "add", str(worktree_path), "-b", branch]
        if start_point:
            add_cmd.append(start_point)

    result = subprocess.run(
        add_cmd, cwd=str(repo_root), capture_output=True, text=True,
    )
    if result.returncode != 0:
        _log.warning(
            "git worktree add failed",
            extra={
                "issue": issue_number,
                "worktree": str(worktree_path),
                "branch": branch,
                "error": result.stderr.strip(),
            },
        )
        return None

    # I-9: neutralise any contaminated shared core.bare for this worktree.
    ensure_per_worktree_core_bare_false(worktree_path, repo_root)

    _log.info(
        "worktree created",
        extra={
            "issue": issue_number,
            "worktree": str(worktree_path),
            "branch": branch,
        },
    )
    return worktree_path


def remove_worktree(
    worktree_path: Path,
    repo_root: Path,
    *,
    force: bool = False,
) -> bool:
    """Remove the git worktree at ``worktree_path`` and prune stale metadata.

    Returns ``True`` when the worktree is no longer registered/present after the
    call, ``False`` when removal failed.
    """
    worktree_path = Path(worktree_path)
    repo_root = Path(repo_root)

    cmd = ["git", "worktree", "remove", str(worktree_path)]
    if force:
        cmd.append("--force")

    result = subprocess.run(
        cmd, cwd=str(repo_root), capture_output=True, text=True,
    )
    if result.returncode != 0:
        _log.warning(
            "git worktree remove failed",
            extra={"worktree": str(worktree_path), "error": result.stderr.strip()},
        )
        return False

    # Prune any dangling administrative entries left behind.
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    return not worktree_path.exists()
