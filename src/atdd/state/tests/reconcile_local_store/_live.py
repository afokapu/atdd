# URN: component:reconcile-local-store:test-support:live_cli:backend:tests
# Runtime: python
# Purpose: Drive the real in-tree `atdd state` CLI by subprocess against real clones of a real bare git remote — the SMOKE/integration harness for reconcile-local-store.

"""Live-CLI harness for the reconcile-local-store SMOKE acceptances (#1400).

The SMOKE acceptances must exercise the *real* command surface against *real*
checkouts and a *real* ``.atdd/state/state.sqlite`` — not an in-process library call.
So this builds a **bare git remote** and clones off it, and drives ``python -m atdd
state ...`` by subprocess, exactly as a developer would.

The bare remote is the point. It has no GitHub, no API, no provider — nothing but git
object storage. If the A/B collaboration flow completes against it, the hot path is
provider-free, and that is not an assertion about the code: it is a property of the
fixture (I7, spec §2.2).

``CI=true`` and a ``HOME`` pinned inside ``tmp_path`` keep the run hermetic: it can
neither read nor write the developer's real store.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple

from atdd.state.bare_remote import clone_of, seed_bare_remote

#: The in-tree ``src/`` root, so the subprocess drives THIS working copy's CLI.
_SRC = Path(__file__).resolve().parents[4]


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True, timeout=60,
    )
    return result.stdout.strip()


def atdd_state(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run ``atdd state <args>`` in ``root`` and capture its result."""
    env = {
        "PYTHONPATH": str(_SRC),
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(root),
        "CI": "true",
    }
    return subprocess.run(
        [sys.executable, "-m", "atdd", "state", *args, "--root", str(root)],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=180,
    )


def bare_remote(tmp_path: Path) -> Path:
    """A bare git remote carrying ``main`` with a Control Root and an empty projection.

    No GitHub, no API, no provider — git object storage and nothing else.
    """
    return seed_bare_remote(tmp_path)


def clone(remote: Path, path: Path) -> Path:
    """A working clone of ``remote`` with a pinned git identity."""
    return clone_of(remote, path)


def two_developers(tmp_path: Path) -> Tuple[Path, Path, Path]:
    """The A/B fixture: a bare remote and two independent clones. Returns (remote, a, b)."""
    remote = bare_remote(tmp_path)
    dev_a = clone(remote, tmp_path / "dev-a")
    dev_b = clone(remote, tmp_path / "dev-b")
    return remote, dev_a, dev_b


def commit(repo: Path, message: str) -> str:
    """Commit everything in ``repo`` locally; return the new sha."""
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def commit_push(repo: Path, message: str) -> str:
    """Commit everything in ``repo`` and push it to ``main``; return the new sha."""
    sha = commit(repo, message)
    _git(repo, "push", "--quiet", "origin", "main")
    return sha


def pull(repo: Path) -> str:
    """Pull ``main`` (a real merge-based pull); return the new HEAD."""
    _git(repo, "pull", "--quiet", "--no-rebase", "origin", "main")
    return _git(repo, "rev-parse", "HEAD")


def head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def git_tracked(repo: Path) -> list:
    """Every file git is tracking. The store must never appear here (spec §2.1)."""
    return _git(repo, "ls-files").splitlines()
