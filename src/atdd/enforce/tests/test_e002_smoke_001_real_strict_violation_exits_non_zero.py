# URN: test:enforce-conventions-ci:E002-SMOKE-001-real-strict-violation-exits-non-zero
# Acceptance: acc:enforce-conventions-ci:E002-SMOKE-001-real-strict-violation-exits-non-zero
# WMBT: wmbt:enforce-conventions-ci:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:enforce-conventions-ci:E002-SMOKE-001-real-strict-violation-exits-non-zero.

End to end, through a REAL process, exactly as CI invokes it:

    python -m atdd enforce --repo-root <root> --paths consumer

over a REAL substrate — a real vendored workspace provider CLI (the actual
subprocess boundary), a real bound STRICT convention node, a real binding lock —
whose detector reports a real violation. The PROCESS must exit non-zero.

This is the propagation the blocking CI job (#1428 E001) rests on. It is proven
against the CODE UNDER TEST, not the pipx-installed toolkit: the child's PYTHONPATH
is this repo's ``src/`` (the #1298 self-deception this row exists to rule out). No
mocks, no monkeypatching, no collaborator substitution — a real child process's
real exit status.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from atdd.coach.utils.repo import find_repo_root

from .conftest import build_content_sensitive_substrate


def _run_enforce(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        # Prove the behaviour against THIS tree, not whatever atdd is installed.
        "PYTHONPATH": str(find_repo_root() / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "atdd", "enforce", "--repo-root", str(root), *args],
        env=env,
        capture_output=True,
        text=True,
    )


def test_real_strict_violation_exits_non_zero(tmp_path: Path) -> None:
    root = build_content_sensitive_substrate(tmp_path)

    proc = _run_enforce(root, "--paths", "dirty")

    # THE assertion the whole wagon exists for: a strict node's violation reaches
    # the shell as a non-zero exit status.
    assert proc.returncode != 0, (
        f"`atdd enforce` exited 0 over a real strict violation — a blocking CI job "
        f"would report SUCCESS on a failing repository.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert proc.returncode == 1, f"expected verdict exit 1, got {proc.returncode}"

    # The failure is diagnosable, not just a red build: the report names the rule.
    assert "acme.rule.owned" in proc.stdout, proc.stdout
    assert "FAIL" in proc.stdout, proc.stdout


def test_real_clean_scan_exits_zero(tmp_path: Path) -> None:
    root = build_content_sensitive_substrate(tmp_path)

    proc = _run_enforce(root, "--paths", "clean")

    assert proc.returncode == 0, (
        f"`atdd enforce` exited non-zero over a clean tree — the gate would be "
        f"unusable.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "PASS" in proc.stdout, proc.stdout
