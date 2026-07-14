# URN: component:migrate-projection-authority:test-support:live_cli:backend:tests
# Runtime: python
# Purpose: Drive the real in-tree `atdd state` CLI by subprocess against a real checkout — the SMOKE harness for migrate-projection-authority.

"""Live-CLI harness for the migrate-projection-authority SMOKE acceptances (#1400).

The SMOKE tests must exercise the *real* command surface against a *real* checkout, a *real*
``.atdd/state/state.sqlite`` and a *real* ``.atdd/manifest.yaml`` — not an in-process call into the
library. So they build a Control Root under ``tmp_path`` and drive ``python -m atdd state ...`` by
subprocess, exactly as an operator following the runbook would.

``CI=true`` and a ``HOME`` pinned inside ``tmp_path`` keep the run hermetic: it can neither read nor
write the developer's real store. No provider is registered and no GitHub remote exists, which is
the point — the migration must complete with the provider world entirely absent (I7).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .._fixtures import make_checkout  # re-exported: the acceptances import it from here

#: The in-tree ``src/`` root, so the subprocess drives THIS working copy's CLI.
_SRC = Path(__file__).resolve().parents[4]

#: The repo this working copy lives in — the source of the runbook and the rollout plan, which the
#: D001/P001 SMOKEs check through the shipped command against the real authored documents.
REPO_ROOT = _SRC.parent


def atdd_state(root: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run ``atdd state <args> --root <root>`` and capture its result."""
    env = {
        "PYTHONPATH": str(_SRC),
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(root),
        "CI": "true",
    }
    return subprocess.run(
        [sys.executable, "-m", "atdd", "state", *args, "--root", str(root)],
        cwd=str(cwd or root), env=env, capture_output=True, text=True, timeout=180,
    )


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in ``root``."""
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, timeout=60,
    )


def commit_all(root: Path, message: str) -> None:
    """Stage and commit everything in ``root`` (identity pinned so the run is hermetic)."""
    git(root, "config", "user.email", "migration@atdd.test")
    git(root, "config", "user.name", "Migration Test")
    git(root, "add", "-A")
    git(root, "commit", "--quiet", "-m", message)


def porcelain(root: Path, paths: Sequence[str] = ()) -> str:
    """``git status --porcelain`` over ``paths`` — empty means "the re-run changed nothing"."""
    return git(root, "status", "--porcelain", "--", *paths).stdout.strip()
