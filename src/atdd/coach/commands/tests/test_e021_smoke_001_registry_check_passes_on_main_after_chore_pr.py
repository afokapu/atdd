# URN: test:govern-lifecycle:systemic-registry-drift-enforcement:E021-SMOKE-001-registry-check-passes-on-main-after-chore-pr
# Acceptance: acc:govern-lifecycle:E021-SMOKE-001-registry-check-passes-on-main-after-chore-pr
# WMBT: wmbt:govern-lifecycle:E021
# Phase: SMOKE
# Layer: backend.smoke
"""
AC-SMOKE-001: After the one-shot resync chore PR lands on main,
atdd registry update --check on main exits 0 and GT-850 no longer requires --force.

Given:
  - atdd CLI installed from the merged main branch
  - The chore PR has been merged (plan/_wagons.yaml, plan/_trains.yaml,
    contracts/_artifacts.yaml updated to match source-of-truth)

When:
  - atdd registry update --check is invoked at the worktree root

Then:
  - Exit code is 0
  - Output reports 'No drift detected' or equivalent
  - GT-850 (COMPLETE gate) no longer requires --force to pass

RED state: As of 2026-05-20, the live branch/main has known registry drift across
6 wagons, 2 trains, and 4 artifact schemas. The one-shot resync chore PR has NOT
been merged yet. This smoke test FAILS until that PR lands on main.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__)
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _run_check(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["atdd", "registry", "update", "--check"],
        capture_output=True,
        text=True,
        cwd=str(root),
    )


def test_registry_check_exits_zero_on_live_branch():
    """atdd registry update --check exits 0 on the live branch after one-shot resync PR.

    RED: As of 2026-05-20 the repo has drift (6 wagons, 2 trains, 4 artifacts out of sync).
    This test fails until `atdd registry update --yes` is committed and merged to main.
    """
    root = _repo_root()
    result = _run_check(root)
    output = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"atdd registry update --check must exit 0 after the one-shot resync PR lands.\n"
        f"Exit code: {result.returncode}\n"
        f"This test is RED until `atdd registry update --yes` is committed (issue #817 Phase 1).\n"
        f"Output:\n{output}"
    )


def test_registry_check_output_reports_no_drift():
    """Output of atdd registry update --check on main must indicate no drift anywhere.

    RED: Current output contains '⚠️  Drift detected' for wagons, trains, and contracts
    because the one-shot resync PR has not landed. After the resync PR merges, no
    '⚠️  Drift detected' lines will appear in the output.
    """
    root = _repo_root()
    result = _run_check(root)
    output = result.stdout + result.stderr
    assert "⚠️  Drift detected" not in output, (
        "Found '⚠️  Drift detected' in check output — registry is still drifted.\n"
        f"This test is RED until the one-shot resync PR (issue #817 Phase 1) lands.\n"
        f"Actual output:\n{output}"
    )


def test_gt850_gate_exits_zero_without_force():
    """atdd registry update --check (the GT-850 gate) exits 0 — no --force bypass needed.

    This verifies the specific lived failure: #813 required `atdd update 794 --status COMPLETE --force`
    because GT-850 detected registry drift on main. After the resync PR, --force must be unnecessary.
    """
    root = _repo_root()
    result = _run_check(root)
    assert result.returncode == 0, (
        f"GT-850 (atdd registry update --check) must exit 0 so COMPLETE transitions do not "
        f"require --force. Exit code: {result.returncode}\n"
        f"Output:\n{result.stdout + result.stderr}"
    )
