# URN: test:train:0306-resolve-object-conflict:E2E-001-resolve-object-conflict-journey
# Train: train:0306-resolve-object-conflict
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: End-to-end journey for the exception-path train — two branches change the
#          SAME projection object. Disjoint objects merge cleanly by uid sharding; a
#          same-object divergence is an EXPECTED failure handled gracefully. The merge
#          driver auto-merges only when the transitions are identical, one side is a
#          strict no-op, or the further phase carries verifiable evidence for every
#          skipped gate. Otherwise it conflicts by design and emits a report — never
#          blind max-phase (section 7.2).
#
# STATUS: RED (xfail-strict). Fails until govern-projection-fields (M4) ships the
#         merge driver. Drop the marker when it xpasses. Refs #1400.
"""Exception-path E2E: same-object divergence -> validity-gated merge or conflict."""
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
@pytest.mark.xfail(strict=True, reason="train 0306-resolve-object-conflict not yet implemented (RED; #1400)")
def test_same_object_conflict_is_validity_gated(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / ".atdd").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)

    # A same-object divergence must be gated by the merge driver, never max-phase.
    res = _atdd(["--repo", str(project), "state", "merge-driver", "--check"], project)
    # Unsafe divergence conflicts by design with an actionable report (non-zero).
    assert res.returncode != 0
    assert "blind" not in res.stdout.lower()
    assert "conflict" in (res.stdout + res.stderr).lower()
