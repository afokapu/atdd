"""
Orphan worktree garbage collector for ATDD.

Detects sibling-of-main directories that were created by `atdd branch` or
`atdd orchestrate` but whose worktree was never properly linked (i.e. not in
`git worktree list`) and whose only file is `.launch_prompt.txt`.

Usage:
    atdd worktree gc             # list orphans (dry-run)
    atdd worktree gc --apply     # remove orphans
"""
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Set


def _real_worktree_paths(repo_root: Path) -> Set[Path]:
    """Return the set of absolute paths registered in git worktree list."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=15,
            cwd=repo_root,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return set()

    paths: Set[Path] = set()
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            paths.add(Path(line[len("worktree "):].strip()).resolve())
    return paths


def _is_orphan(path: Path, worktree_paths: Set[Path]) -> bool:
    """Return True if path is an atdd orphan dir safe to remove.

    Orphan = all of:
    - is a directory
    - NOT in the real git worktree list
    - contains exactly one file: .launch_prompt.txt (no other files anywhere)
    """
    resolved = path.resolve()
    if not resolved.is_dir():
        return False
    if resolved in worktree_paths:
        return False

    all_files = list(resolved.rglob("*"))
    non_dir_files = [f for f in all_files if f.is_file()]

    if len(non_dir_files) != 1:
        return False
    if non_dir_files[0].name != ".launch_prompt.txt":
        return False

    return True


def gc(repo_root: Optional[Path] = None, apply: bool = False) -> List[Path]:
    """Detect (and optionally remove) orphan worktree dirs at the project parent.

    Scans every immediate sibling of repo_root's parent directory that matches
    the flat-worktree naming convention (contains a hyphen, e.g. feat-my-slug).
    Only dirs that are NOT in `git worktree list` AND contain only
    `.launch_prompt.txt` are classified as orphans.

    Args:
        repo_root: Root of the main checkout. Defaults to cwd.
        apply: When True, rm-rf each orphan. When False (default), list only.

    Returns:
        List of orphan paths detected (regardless of apply).
    """
    if repo_root is None:
        repo_root = Path.cwd()
    repo_root = Path(repo_root).resolve()

    parent = repo_root.parent
    worktree_paths = _real_worktree_paths(repo_root)

    orphans: List[Path] = []
    for candidate in sorted(parent.iterdir()):
        if candidate == repo_root:
            continue
        if not candidate.is_dir():
            continue
        if "-" not in candidate.name:
            continue
        if _is_orphan(candidate, worktree_paths):
            orphans.append(candidate)

    if apply:
        for orphan in orphans:
            shutil.rmtree(orphan)

    return orphans
