# URN: test:reconcile-local-store:trigger-head-hooks:M001-SMOKE-001-head-change-reconcile
# Acceptance: acc:reconcile-local-store:M001-SMOKE-001-head-change-reconcile
# WMBT: wmbt:reconcile-local-store:M001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real post-merge hook, installed into a real checkout's core.hooksPath, fires on a real `git merge` and reconciles the real store to the new HEAD without blocking git. Refs #1400.
"""SMOKE — a real git merge fires the real hook (M001-SMOKE-001).

wagon: reconcile-local-store | feature: trigger-head-hooks | phase: SMOKE
WMBT: wmbt:reconcile-local-store:M001

The unit acceptance runs the hook script directly. This one lets *git* run it: the real
hook template is installed at ``core.hooksPath`` in a real checkout, and a real ``git
merge`` moves HEAD. What is being proved is the wiring — that the hook is named what git
expects, is executable, and is found — which no amount of testing the script's body can
establish. Refs #1400.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.state import metadata

from ._helpers import UID_A, checkout, commit_all, document, git, head, store, write_projection

#: The hook templates `atdd init` installs.
_TEMPLATES = Path(__file__).resolve().parents[3] / "coach" / "templates" / "hooks"

#: The in-tree ``src/`` root, so the hook's `atdd` drives THIS working copy.
_SRC = Path(__file__).resolve().parents[4]


def _install_hooks(repo: Path) -> Path:
    """Install the real hook templates and point git at them, as `atdd init` does."""
    hooks = repo / ".atdd" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    for name in ("post-merge", "post-checkout", "post-rewrite", "pre-rebase"):
        dst = hooks / name
        shutil.copy2(_TEMPLATES / name, dst)
        dst.chmod(0o755)
    git(repo, "config", "core.hooksPath", str(hooks))
    return hooks


def _atdd_shim(repo: Path) -> Path:
    """A real `atdd` on PATH that runs THIS working copy's CLI — what the hook invokes."""
    bindir = repo / ".bin"
    bindir.mkdir(exist_ok=True)
    shim = bindir / "atdd"
    shim.write_text(
        "#!/bin/sh\n"
        f'PYTHONPATH="{_SRC}" exec "{sys.executable}" -m atdd "$@" --root "{repo}"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return bindir


@pytest.mark.smoke
def test_m001_smoke_001_head_change_reconcile(tmp_path) -> None:
    """A real `git merge` fires the real post-merge hook, which reconciles the real store."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED", owner="dev-a")])
    base = commit_all(repo, "base projection")

    from ._live import atdd_state

    assert atdd_state(repo, "hydrate").returncode == 0

    hooks = _install_hooks(repo)
    assert (hooks / "post-merge").exists()
    assert os.access(hooks / "post-merge", os.X_OK)

    # A peer's work lands on a side branch.
    git(repo, "checkout", "--quiet", "-b", "peer")
    write_projection(repo, [document(UID_A, phase="GREEN", owner="dev-a")])
    peer_head = commit_all(repo, "peer: advance to GREEN")
    git(repo, "checkout", "--quiet", "-")

    # The store is still anchored to the base commit; nothing has reconciled it yet.
    conn = store(repo)
    try:
        assert metadata.base_commit(conn) == base
    finally:
        conn.close()

    # A REAL git merge. Git finds and runs the real post-merge hook itself.
    env = dict(os.environ)
    env["PATH"] = f"{_atdd_shim(repo)}:{env.get('PATH', '')}"
    env.pop("CI", None)  # the hook no-ops under CI=true; here we want it to fire
    merged = subprocess.run(
        ["git", "merge", "--no-edit", "peer"],
        cwd=str(repo), env=env, capture_output=True, text=True, timeout=180,
    )

    # A hook failure must never block the merge — and this one did not fail.
    assert merged.returncode == 0, merged.stdout + merged.stderr
    assert head(repo) == peer_head

    # The hook reconciled the real store: it is anchored at the new HEAD, and carries
    # the peer's merged state. Nobody ran `atdd state reconcile` by hand.
    conn = store(repo)
    try:
        assert metadata.base_commit(conn) == peer_head
        row = conn.execute("SELECT state FROM objects WHERE uid=?", (UID_A,)).fetchone()
        assert row["state"] == "GREEN"
    finally:
        conn.close()

    fresh = atdd_state(repo, "freshness")
    assert fresh.returncode == 0, fresh.stdout
    assert "fresh" in fresh.stdout
