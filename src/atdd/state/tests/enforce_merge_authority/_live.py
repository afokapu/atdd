# URN: component:enforce-merge-authority:test-support:live_cli:backend:tests
# Runtime: python
# Purpose: Drive the real in-tree `atdd state` merge-authority CLI by subprocess against real checkouts of a real BARE (non-GitHub) git remote — the SMOKE/integration harness for enforce-merge-authority.

"""Live-CLI harness for the enforce-merge-authority SMOKE acceptances (#1400).

The SMOKE acceptances must exercise the *real* command surface against a *real* checkout —
not an in-process library call. So this drives ``python -m atdd state ...`` by subprocess,
exactly as a CI job would.

The remote is **bare**: git object storage, no GitHub, no API, no provider. That is the
point of the fixture rather than an incidental detail — if the merge-authority run rejects
a canonical-but-illegal branch against a bare remote, then CI's authority is git's, not
GitHub's, and the gate is real wherever the code is hosted (I7, spec §4).

``CI=true`` and a ``HOME`` pinned inside ``tmp_path`` keep the run hermetic: it can neither
read nor write the developer's real store.
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

#: The repository root — the policy and the workflow the CLI reads live there.
_REPO = Path(__file__).resolve().parents[5]


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True, timeout=60,
    )
    return result.stdout.strip()


def atdd_state(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run ``atdd state <args> --root <root>`` and capture its result."""
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
    """A bare git remote carrying ``main``: git object storage and nothing else."""
    return seed_bare_remote(tmp_path)


def clone(remote: Path, path: Path) -> Path:
    """A working clone of ``remote`` with a pinned git identity."""
    return clone_of(remote, path)


def repo_on_bare_remote(tmp_path: Path) -> Tuple[Path, Path]:
    """``(remote, checkout)`` — a bare remote and one clone of it, both hermetic."""
    remote = bare_remote(tmp_path)
    return remote, clone(remote, tmp_path / "work")


def install_policy(root: Path) -> None:
    """Copy this working copy's real policy + workflow into a fixture checkout.

    The SMOKEs exercise the *shipped* policy and the *shipped* workflow, not a fixture's
    idea of them: a policy that only exists in a test proves nothing about the branch a
    merge actually lands on.
    """
    for relative in (
        Path(".github") / "atdd-merge-authority-policy.yaml",
        Path(".github") / "workflows" / "atdd-merge-authority.yml",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((_REPO / relative).read_bytes())


def commit(repo: Path, msg: str) -> str:
    """Commit everything in ``repo``; return the new sha.

    ``--allow-empty`` because several acceptances re-commit the *same tree* under a
    different message: the trailer group is the thing under test, and a commit that
    changes nothing but its trailers is exactly the case the cross-check must judge.
    """
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def push(repo: Path, branch: str = "main") -> None:
    _git(repo, "push", "--quiet", "origin", branch)


def branch(repo: Path, name: str) -> None:
    _git(repo, "checkout", "--quiet", "-b", name)


def head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")
