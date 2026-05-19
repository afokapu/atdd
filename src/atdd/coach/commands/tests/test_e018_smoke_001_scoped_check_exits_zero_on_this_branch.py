# URN: test:govern-lifecycle:pr-scoped-registry-drift-gate:E018-SMOKE-001-scoped-check-exits-zero-on-this-branch
# Acceptance: acc:govern-lifecycle:E018-SMOKE-001-scoped-check-exits-zero-on-this-branch
# WMBT: wmbt:govern-lifecycle:E018
# Phase: SMOKE
# Layer: backend.smoke
"""
AC-SMOKE-001: atdd registry update --check --scope changed-files exits 0 on the live
#582 branch (only govern-lifecycle wagon source changed, aggregate synced in this PR).
"""
import subprocess
import sys
import os
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__)
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def test_scoped_check_exits_zero_on_live_branch():
    """atdd registry update --check --scope changed-files exits 0 on this PR branch."""
    root = _repo_root()
    src = str(root / "src")
    env = os.environ.copy()
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "atdd", "registry", "update", "--check", "--scope", "changed-files"],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"Scoped GT-002 check exited {result.returncode}:\n{output}"
    )
    assert "in sync" in output.lower() or "trivial pass" in output.lower() or "no wagon" in output.lower(), (
        f"Expected pass notice in output:\n{output}"
    )
