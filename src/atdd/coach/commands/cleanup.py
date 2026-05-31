# URN: component:govern-lifecycle:enforcement-substrate:cleanup:backend:domain
# Runtime: python
# Purpose: `atdd cleanup` — detect + remove merged-but-not-removed worktrees and orphan
#          branches (#928 Gap 2), so dangling post-merge worktrees stop accumulating.
"""
``atdd cleanup`` — garbage-collect merged worktrees + orphan branches.

After a PR merges, its worktree and branch are routinely left behind. They
accumulate (this session found 13 dangling), clutter ``git worktree list``,
and — combined with the core.bare bleed (#917) — are extra surfaces for
phantom-deletion poisoning. ``atdd worktree gc`` only removes non-git scratch
dirs (``.launch_prompt.txt`` orphans); it does NOT touch a real linked
worktree whose branch has already merged. This command fills that gap (#928
Gap 2).

A branch counts as **merged** iff it has a MERGED pull request
(``gh pr list --head <branch> --state merged``). This is the only safe
signal:
  * It catches **squash-merges**, where the branch commits never become
    ancestors of ``origin/main`` even though the work landed (the common case
    — the #928-spec ``--is-ancestor`` check misses every squash-merged branch).
  * It does NOT false-positive on **prep worktrees** (a fresh ``atdd issue``
    branch with 0 commits ahead, like #928/#930): its tip equals an old
    ``origin/main`` commit, so ``--is-ancestor`` reports "merged" even though
    it is active prep that must NOT be removed. A prep branch has no merged
    PR, so the PR signal correctly leaves it alone.
Offline (no ``gh``) the PR check returns False → cleanup removes nothing
(fail-safe; never a spurious deletion).

Safety: ``main`` is never touched; a worktree with uncommitted changes is
skipped (never force-removed); default is dry-run.

Usage:
    atdd cleanup            # list merged worktrees + orphan branches (dry-run)
    atdd cleanup --yes      # remove them (worktrees first, then branches)
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

_DEFAULT_BRANCH = "main"


@dataclass(frozen=True)
class Removable:
    """A worktree or branch that cleanup would remove."""

    kind: str          # "worktree" | "branch"
    name: str          # branch name
    path: Optional[str]  # worktree path (None for orphan branches)
    reason: str


def evaluate_worktree_removable(
    *,
    branch: Optional[str],
    is_main: bool,
    branch_merged: bool,
    has_uncommitted: bool,
) -> Tuple[bool, str]:
    """Pure decision: should this worktree be removed? Returns (removable, reason).

    Conservative by design — only removes a worktree whose branch is provably
    merged and which holds no uncommitted work.
    """
    if is_main:
        return False, "main worktree — never removed"
    if branch is None:
        return False, "detached HEAD — skipped (no branch to evaluate)"
    if has_uncommitted:
        return False, "uncommitted changes — skipped (commit or discard first)"
    if branch_merged:
        return True, "merged PR + content fully in main"
    return False, "branch not merged — kept"


# ---------------------------------------------------------------------------
# git / gh IO (best-effort; failures degrade to "unknown", never raise)
# ---------------------------------------------------------------------------
def _git(repo_root: Path, *args: str, timeout: int = 15) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(
            ["git", *args], cwd=repo_root, capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
        return None


def _list_worktrees(repo_root: Path) -> List[Tuple[Path, Optional[str]]]:
    """Return [(path, branch_or_None)] from ``git worktree list --porcelain``."""
    res = _git(repo_root, "worktree", "list", "--porcelain")
    if res is None or res.returncode != 0:
        return []
    out: List[Tuple[Path, Optional[str]]] = []
    path: Optional[Path] = None
    branch: Optional[str] = None
    for line in res.stdout.splitlines() + [""]:
        if line.startswith("worktree "):
            if path is not None:
                out.append((path, branch))
            path = Path(line[len("worktree "):].strip()).resolve()
            branch = None
        elif line.startswith("branch "):
            ref = line[len("branch "):].strip()
            branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    if path is not None:
        out.append((path, branch))
    return out


def _worktree_has_uncommitted(repo_root: Path, path: Path) -> bool:
    res = _git(path, "status", "--porcelain")
    if res is None:
        return True  # can't tell → treat as dirty (conservative: don't remove)
    return bool(res.stdout.strip())


def _has_merged_pr(repo_root: Path, branch: str) -> bool:
    """True if `branch` has a merged PR (catches squash-merges). gh-dependent."""
    try:
        res = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "merged",
             "--json", "number", "--jq", "length"],
            cwd=repo_root, capture_output=True, text=True, timeout=20,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
        return False
    if res.returncode != 0:
        return False
    return res.stdout.strip() not in ("", "0")


def _branch_is_merged(repo_root: Path, branch: str) -> bool:
    # A merged PR is the signal that the branch's work was accepted and landed.
    # `--is-ancestor` is deliberately NOT used: it cannot tell a merged branch
    # from a 0-commit prep branch (#928/#930) and would delete active prep. A
    # content-diff guard was tried and rejected — `git diff origin/main..branch`
    # is non-empty whenever main merely MOVED ON, so it wrongly excludes every
    # older merged branch. The safety net for the rare "commits pushed after the
    # PR merged" case is the default dry-run + explicit `--yes` confirmation.
    return _has_merged_pr(repo_root, branch)


def _local_branches(repo_root: Path) -> List[str]:
    res = _git(repo_root, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    if res is None or res.returncode != 0:
        return []
    return [b for b in res.stdout.split() if b]


def find_removable(repo_root: Path) -> List[Removable]:
    """Return all merged worktrees + orphan merged branches that cleanup would remove."""
    removable: List[Removable] = []
    worktrees = _list_worktrees(repo_root)
    branches_in_worktrees = {b for _, b in worktrees if b}

    for path, branch in worktrees:
        is_main = branch == _DEFAULT_BRANCH or path.name == _DEFAULT_BRANCH
        merged = bool(branch) and _branch_is_merged(repo_root, branch)
        ok, reason = evaluate_worktree_removable(
            branch=branch,
            is_main=is_main,
            branch_merged=merged,
            has_uncommitted=_worktree_has_uncommitted(repo_root, path),
        )
        if ok:
            removable.append(Removable("worktree", branch, str(path), reason))

    # Orphan branches: a local branch not checked out in any worktree, already merged.
    for branch in _local_branches(repo_root):
        if branch == _DEFAULT_BRANCH or branch in branches_in_worktrees:
            continue
        if _branch_is_merged(repo_root, branch):
            removable.append(Removable("branch", branch, None, "orphan branch, merged"))

    return removable


def run_cleanup(apply: bool = False, repo_root: Optional[Path] = None) -> int:
    """CLI entry. Dry-run by default; ``apply=True`` removes. Returns exit code."""
    from atdd.coach.utils.repo import find_repo_root

    root = repo_root or find_repo_root()
    items = find_removable(root)

    if not items:
        print("atdd cleanup: nothing to remove — no merged worktrees or orphan branches.")
        return 0

    worktrees = [i for i in items if i.kind == "worktree"]
    branches = [i for i in items if i.kind == "branch"]

    verb = "Removing" if apply else "Would remove"
    print(f"atdd cleanup: {verb} {len(worktrees)} worktree(s) + {len(branches)} orphan branch(es):\n")
    for i in worktrees:
        print(f"  worktree  {i.path}  [{i.name}] — {i.reason}")
    for i in branches:
        print(f"  branch    {i.name} — {i.reason}")

    if not apply:
        print("\nDry-run. Re-run with --yes to remove (worktrees kept branch refs are also pruned).")
        return 0

    print()
    for i in worktrees:
        res = _git(root, "worktree", "remove", i.path, "--force")
        ok = res is not None and res.returncode == 0
        print(f"  {'removed' if ok else 'FAILED '} worktree {i.path}")
        if ok:
            # Prune the now-unused branch too.
            _git(root, "branch", "-D", i.name)
    for i in branches:
        res = _git(root, "branch", "-D", i.name)
        ok = res is not None and res.returncode == 0
        print(f"  {'deleted' if ok else 'FAILED '} branch {i.name}")
    return 0


__all__ = ["Removable", "evaluate_worktree_removable", "find_removable", "run_cleanup"]
