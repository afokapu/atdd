"""
Git commit helper for atomic manifest writes.

Convention: src/atdd/coach/conventions/issue.convention.yaml (manifest_write_discipline)
Issue: #344

Manifest-mutating CLI verbs (`atdd issue <slug>`, `atdd update --status`,
`atdd archive`) write `.atdd/manifest.yaml` and must commit that write
atomically with the verb. Otherwise a worktree branched from main HEAD
cannot see issues created after that HEAD — breaking `--sync-wmbts` and
any other manifest-reading flow.

The single entry point is `git_commit_manifest_update`. Every call site
funnels through it so the contract is auditable.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ManifestCommitError(RuntimeError):
    """Raised when a manifest commit cannot proceed safely."""


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _current_branch(repo_root: Path) -> Optional[str]:
    result = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo_root)
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def _is_tracked(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root)
    result = _git("ls-files", "--error-unmatch", str(rel), cwd=repo_root)
    return result.returncode == 0


def _has_other_staged_changes(path: Path, repo_root: Path) -> bool:
    """Return True if the index has any staged path other than `path`."""
    rel = str(path.relative_to(repo_root))
    result = _git("diff", "--cached", "--name-only", cwd=repo_root)
    if result.returncode != 0:
        return False
    staged = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return any(p != rel for p in staged)


def _path_has_diff(path: Path, repo_root: Path) -> bool:
    """Return True if the manifest path differs from HEAD (worktree or index)."""
    rel = str(path.relative_to(repo_root))
    # Combined: any worktree-vs-HEAD diff for this single path.
    worktree = _git("diff", "--name-only", "HEAD", "--", rel, cwd=repo_root)
    if worktree.returncode != 0:
        return False
    return bool(worktree.stdout.strip())


def git_commit_manifest_update(
    path: Path,
    message: str,
    verb: str,
    repo_root: Optional[Path] = None,
    allow_main: bool = False,
) -> Optional[str]:
    """Stage and commit a single manifest path atomically.

    Args:
        path: Absolute path to the file to commit (typically `.atdd/manifest.yaml`).
        message: Full commit message body.
        verb: CLI verb name for log/error context (e.g. "atdd issue").
        repo_root: Repo root. Defaults to `path`'s git toplevel.
        allow_main: When False (default), refuse to commit on `main`. The
            on-main rule (CLAUDE.md `git.commit_discipline.on_main_detection`)
            wants the workflow violation surfaced rather than silently
            committed. Pass True only for flows the user has explicitly opted
            into (e.g. a future `--allow-main` flag).

    Returns:
        The new commit's SHA, or None when there is nothing to commit
        (manifest matches HEAD already — a legitimate no-op).

    Raises:
        ManifestCommitError:
            - on `main` without `allow_main`
            - other staged changes already in the index (no surprise bundling)
            - path is not tracked by git
            - underlying git command fails
    """
    path = Path(path).resolve()
    if repo_root is None:
        toplevel = _git("rev-parse", "--show-toplevel", cwd=path.parent)
        if toplevel.returncode != 0:
            raise ManifestCommitError(
                f"{verb}: not inside a git repository (path={path})"
            )
        repo_root = Path(toplevel.stdout.strip()).resolve()
    else:
        repo_root = Path(repo_root).resolve()

    # Tracked-file precondition.
    if not _is_tracked(path, repo_root):
        raise ManifestCommitError(
            f"{verb}: refusing to commit untracked path {path}. "
            f"Add the file to git and try again."
        )

    # Branch precondition.
    branch = _current_branch(repo_root)
    if branch == "main" and not allow_main:
        raise ManifestCommitError(
            f"{verb}: refusing to commit on main. "
            f"Branch off first (e.g. `atdd branch <N>`) or pass allow_main=True."
        )

    # Index-isolation precondition.
    if _has_other_staged_changes(path, repo_root):
        raise ManifestCommitError(
            f"{verb}: refusing to commit — other staged changes exist. "
            f"Unstage them or commit them separately to avoid bundling."
        )

    # No-op: manifest matches HEAD already.
    if not _path_has_diff(path, repo_root):
        logger.debug("%s: manifest unchanged at %s — skipping commit", verb, path)
        return None

    rel = str(path.relative_to(repo_root))
    add = _git("add", "--", rel, cwd=repo_root)
    if add.returncode != 0:
        raise ManifestCommitError(
            f"{verb}: git add failed for {rel}: {add.stderr.strip()}"
        )

    commit = _git("commit", "-m", message, "--", rel, cwd=repo_root)
    if commit.returncode != 0:
        raise ManifestCommitError(
            f"{verb}: git commit failed: {commit.stderr.strip() or commit.stdout.strip()}"
        )

    sha_result = _git("rev-parse", "HEAD", cwd=repo_root)
    if sha_result.returncode != 0:
        raise ManifestCommitError(f"{verb}: could not read commit sha")
    return sha_result.stdout.strip()
