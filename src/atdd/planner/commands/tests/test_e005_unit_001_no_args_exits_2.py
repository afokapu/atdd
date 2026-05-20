# URN: test:define-plans:atdd-plan:E005-UNIT-001-no-args-exits-2
# Acceptance: acc:define-plans:E005-UNIT-001-no-args-exits-2
# WMBT: wmbt:define-plans:E005
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E005-UNIT-001 — atdd plan with no sources exits 2 and prints help."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SRC_ROOT = str(Path(__file__).parent.parent.parent.parent.parent)  # repo/src


def _run_plan(*extra_argv: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = _SRC_ROOT
    return subprocess.run(
        [sys.executable, "-m", "atdd", "plan", *extra_argv],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_no_args_exits_2():
    result = _run_plan()
    assert result.returncode == 2, (
        f"Expected exit code 2, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_no_args_prints_help():
    result = _run_plan()
    combined = result.stdout + result.stderr
    assert "usage" in combined.lower() or "atdd plan" in combined.lower(), (
        f"Expected help output, got:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
