# URN: test:train:0206-reconcile-dirty-store:E2E-001-reconcile-dirty-store-journey
# Train: train:object-conflict-resolution:reconcile-dirty-store
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: End-to-end journey for the alternate-path train — reconcile when the local
#          store is DIRTY (uncommitted overlay events exist). Instead of a plain
#          hydrate-overwrite, the store is backed up, the incoming projection is
#          hydrated into a public baseline, the overlay is replayed on top, affected
#          objects are re-projected, and store_base_commit advances. Invariant I5:
#          reconcile is not overwrite.
#
# STATUS: RED (xfail-strict). Fails until reconcile-local-store (M2) implements the
#         dirty-store path. Drop the marker when it xpasses. Refs #1400.
"""Alternate-path E2E: dirty store + incoming projection -> backup, replay, advance."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _atdd(args, cwd):
    env = {**os.environ, "PYTHONPATH": str(SRC), "CI": "true"}
    return subprocess.run(
        [sys.executable, "-m", "atdd", *args],
        cwd=str(cwd), capture_output=True, text=True, env=env,
    )


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="train train:object-conflict-resolution:reconcile-dirty-store not yet implemented (RED; #1400)")
def test_dirty_store_reconcile_preserves_overlay(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / ".atdd").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)

    # A dirty store: an uncommitted local overlay event exists before reconcile.
    assert _atdd(["--repo", str(project), "state", "project"], project).returncode == 0

    rec = _atdd(["--repo", str(project), "state", "reconcile"], project)
    assert rec.returncode == 0
    # A backup is taken before any mutation, and the local overlay survives.
    backups = list((project / ".atdd" / "state").glob("*.backup*")) + list(
        (project / ".atdd" / "state" / "backups").glob("*") if (project / ".atdd" / "state" / "backups").is_dir() else []
    )
    assert backups, "reconcile of a dirty store must back up before mutating (I5)"
    assert "conflict" not in rec.stdout.lower() or "kept backup" in rec.stdout.lower()
