"""Git object storage as a projection repository (#1400 reconcile-local-store).

Reconcile needs to answer three questions about the *repository*, not about the
store: where is HEAD, is the store's base commit still reachable, and what did the
projection look like at a given commit. This module is the only place in core that
asks git, and it asks by subprocess — no library, no provider, no network.

That matters for more than tidiness: the whole collaboration model must work
against a **bare git remote with no GitHub API reachable** (spec §2.2, I7). Every
call here is satisfiable by `git` alone, so the reconcile hot path stays provider-
free by construction.

Dependency discipline: stdlib only.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from atdd.state.projection import PROJECTION_RELATIVE, PROJECTION_SUFFIX

_log = logging.getLogger(__name__)

#: Long enough that a runaway `git` cannot wedge a hook, short enough that an
#: operator notices. Every call here is a local object-store read.
_TIMEOUT = 30


class GitError(RuntimeError):
    """A git invocation failed, or the directory is not a repository."""


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo), capture_output=True, text=True, timeout=_TIMEOUT,
    )
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}")
    return result


def head(repo: Path) -> str:
    """The commit HEAD names — the commit the working tree is currently at."""
    return _git(Path(repo), "rev-parse", "HEAD").stdout.strip()


def commit_exists(repo: Path, commit: str) -> bool:
    """True when ``commit`` is a commit object reachable in this repository.

    A base commit that no longer resolves means the store is anchored to history
    this checkout does not have (a discarded branch, a hard reset, a fresh clone).
    Reconcile must refuse rather than replay onto the wrong public state (P001).
    """
    result = _git(
        Path(repo), "cat-file", "-e", f"{commit}^{{commit}}", check=False,
    )
    return result.returncode == 0


def projection_at(repo: Path, commit: str) -> Dict[str, str]:
    """Every ``<uid>.yaml`` in the projection at ``commit``, as ``{filename: text}``.

    Read straight out of git object storage, so it reports what that commit
    *committed* — never what the working tree happens to hold right now.
    """
    repo = Path(repo)
    prefix = PROJECTION_RELATIVE.as_posix()
    listing = _git(repo, "ls-tree", "--name-only", f"{commit}:{prefix}", check=False)
    if listing.returncode != 0:
        return {}  # the commit predates the projection directory
    documents: Dict[str, str] = {}
    names: List[str] = [
        name for name in listing.stdout.splitlines() if name.endswith(PROJECTION_SUFFIX)
    ]
    for name in sorted(names):
        blob = _git(repo, "show", f"{commit}:{prefix}/{name}")  # noqa: N+1 — one blob per file
        documents[name] = blob.stdout
    return documents


def toplevel(start: Optional[Path] = None) -> Path:
    """The repository root containing ``start`` (default: cwd)."""
    where = Path(start) if start is not None else Path.cwd()
    return Path(_git(where, "rev-parse", "--show-toplevel").stdout.strip())
