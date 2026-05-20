# URN: test:define-plans:atdd-plan:C001-UNIT-001-json-output-has-correct-keys
# Acceptance: acc:define-plans:C001-UNIT-001-json-output-has-correct-keys
# WMBT: wmbt:define-plans:C001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C001-UNIT-001 — --json emits valid stderr JSON with sources and brief_out only."""
from __future__ import annotations

import json
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


def test_json_output_has_correct_keys():
    result = _run_plan("--text", "x", "--json")
    assert result.returncode == 0, (
        f"Command failed with code {result.returncode}\nstderr: {result.stderr}"
    )

    data = json.loads(result.stderr)
    assert "sources" in data, "Missing 'sources' key in --json output"
    assert "brief_out" in data, "Missing 'brief_out' key in --json output"

    forbidden = {"artifact_created", "worktree", "branch"}
    found_forbidden = forbidden & set(data.keys())
    assert not found_forbidden, (
        f"--json output must not include git-mechanic fields: {found_forbidden}"
    )
