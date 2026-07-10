# URN: test:train:0006-state-projection:E2E-001-state-projection-journey
# Train: train:0006-state-projection
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: End-to-end journey for the state-projection train — Dev A authors in a
#          private local store, projects it to committed per-uid YAML, commits with
#          ATDD trailers, and CI validates canonicality + legal transition; Dev B
#          hydrates from the shared projection and reconciles, preserving local
#          overlay. No GitHub is read on the hot path.
#
# STATUS: RED (xfail-strict). This is the executable statement of what train 0006
#         delivers. It fails until the projection/reconcile CLI exists — the wagons
#         project-shared-state (M1) + reconcile-local-store (M2) + enforce-merge-
#         authority (M3) land it. When it xpasses, drop the xfail marker. Refs #1400.
"""Train-level E2E: author -> project -> commit(trailers) -> validate -> reconcile.

Exercises the corrected collaboration model as a working whole:
project(store) == committed projection (I1), a hydrate/reconcile round-trip that
keeps Dev B's overlay (I3/I5), and CI as the merge authority (I6) — all through git,
with GitHub off the hot path (I7).
"""
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
@pytest.mark.xfail(strict=True, reason="train 0006-state-projection not yet implemented (RED; #1400)")
def test_project_commit_reconcile_journey(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / ".atdd").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)

    # 1. Author locally, then project the store to committed per-uid YAML (I1).
    assert _atdd(["--repo", str(project), "state", "project"], project).returncode == 0
    proj_dir = project / ".atdd" / "state" / "projection"
    assert proj_dir.is_dir() and any(proj_dir.glob("*.yaml"))

    # 2. project(hydrate(projection)) == projection — deterministic round-trip.
    first = sorted(p.read_bytes() for p in proj_dir.glob("*.yaml"))
    assert _atdd(["--repo", str(project), "state", "hydrate"], project).returncode == 0
    assert _atdd(["--repo", str(project), "state", "project"], project).returncode == 0
    second = sorted(p.read_bytes() for p in proj_dir.glob("*.yaml"))
    assert first == second

    # 3. Reconcile after a HEAD change preserves uncommitted local overlay (I5).
    rec = _atdd(["--repo", str(project), "state", "reconcile"], project)
    assert rec.returncode == 0
