# URN: test:author-atdd-substrate:substrate-spine:C001-SMOKE-001-cli-refuses-bad-input
# Acceptance: acc:author-atdd-substrate:C001-SMOKE-001-cli-refuses-bad-input
# WMBT: wmbt:author-atdd-substrate:C001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C001-SMOKE-001 — the real `atdd author` CLI refuses bad input and writes nothing.

Real-infrastructure smoke: invokes the actual CLI entry point as a
subprocess (no fakes), from an isolated temp cwd, and asserts that each
malformed input exits non-zero and leaves no artifact on disk.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[4]  # .../src


def _run(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": _path_env(), "HOME": str(cwd)}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _path_env():
    import os

    return os.environ.get("PATH", "")


@pytest.mark.parametrize(
    "args, field",
    [
        (["convention-node", "--role", "nonsense", "--rule-id", "nonsense.green.foo"], "role"),
        (["convention-node", "--role", "coder", "--rule-id", "coder.Green.BAD_ID"], "rule_id"),
        (["convention-node", "--role", "coder", "--rule-id", "tester.green.foo"], "rule_id"),
    ],
)
def test_cli_refuses_bad_input(tmp_path, args, field):
    result = _run(args, tmp_path)
    assert result.returncode != 0, f"expected non-zero exit, got 0\n{result.stderr}"
    assert "atdd author:" in result.stderr
    # nothing authored to disk under the isolated cwd
    assert not (tmp_path / "src").exists(), "CLI wrote an artifact for invalid input"
