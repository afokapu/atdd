# URN: test:define-plans:atdd-plan:C001-UNIT-001-json-output-has-correct-keys
# Acceptance: acc:define-plans:C001-UNIT-001-json-output-has-correct-keys
# WMBT: wmbt:define-plans:C001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C001-UNIT-001 — --json emits valid stderr JSON with sources and brief_out only."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest


def test_json_output_has_correct_keys():
    result = subprocess.run(
        [sys.executable, "-m", "atdd", "plan", "--text", "x", "--json"],
        capture_output=True,
        text=True,
    )
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
