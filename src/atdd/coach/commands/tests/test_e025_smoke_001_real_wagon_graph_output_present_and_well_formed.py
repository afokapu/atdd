# URN: test:spawn-agents:E025-SMOKE-001-real-wagon-graph-output-present-and-well-formed
# Acceptance: acc:spawn-agents:E025-SMOKE-001-real-wagon-graph-output-present-and-well-formed
# WMBT: wmbt:spawn-agents:E025
# Phase: SMOKE
# Layer: smoke
"""E025-SMOKE-001 — `atdd repo graph --wagon spawn-agents --format launch-prompt`
against the live installed package emits a well-formed, non-empty markdown string
that is ≤ 2 KB and contains the wagon name.

Phase RED: subprocess exits non-zero because '--format launch-prompt' is not yet
a recognised choice for `atdd repo graph` (current choices: json, dot, prompt).
Phase GREEN/SMOKE: command exits 0, stdout is non-empty, ≤ 2 048 bytes,
contains 'spawn-agents' or 'Spawn Agents', no Python traceback present.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.slow]

_REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
_MAX_BYTES = 2048


def test_cli_exits_zero() -> None:
    """atdd repo graph --wagon spawn-agents --format launch-prompt must exit 0."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "atdd",
            "repo",
            "graph",
            "--wagon",
            "spawn-agents",
            "--format",
            "launch-prompt",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, (
        "Expected exit code 0 for `atdd repo graph --wagon spawn-agents "
        "--format launch-prompt`.\n"
        f"Exit code: {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


def test_cli_stdout_is_non_empty() -> None:
    """stdout must be non-empty."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "atdd",
            "repo",
            "graph",
            "--wagon",
            "spawn-agents",
            "--format",
            "launch-prompt",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert result.stdout.strip(), (
        "Expected non-empty stdout. "
        f"stderr: {result.stderr}"
    )


def test_cli_output_under_2kb() -> None:
    """stdout must be ≤ 2 048 bytes."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "atdd",
            "repo",
            "graph",
            "--wagon",
            "spawn-agents",
            "--format",
            "launch-prompt",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    byte_len = len(result.stdout.encode("utf-8"))
    assert byte_len <= _MAX_BYTES, (
        f"Output is {byte_len} bytes, exceeds 2 048-byte budget.\n"
        f"stdout:\n{result.stdout}"
    )


def test_cli_output_contains_wagon_name() -> None:
    """stdout must contain 'spawn-agents' or 'Spawn Agents'."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "atdd",
            "repo",
            "graph",
            "--wagon",
            "spawn-agents",
            "--format",
            "launch-prompt",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert "spawn-agents" in result.stdout or "Spawn Agents" in result.stdout, (
        "Expected wagon identifier in output.\n"
        f"stdout:\n{result.stdout}"
    )


def test_cli_output_contains_no_traceback() -> None:
    """stdout must not contain a Python traceback."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "atdd",
            "repo",
            "graph",
            "--wagon",
            "spawn-agents",
            "--format",
            "launch-prompt",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    combined = result.stdout + result.stderr
    assert "Traceback (most recent call last)" not in combined, (
        "Output contains a Python traceback — the command crashed.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
