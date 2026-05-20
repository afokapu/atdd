# URN: test:define-plans:atdd-plan:C001-UNIT-002-json-sources-reflect-parsed-input
# Acceptance: acc:define-plans:C001-UNIT-002-json-sources-reflect-parsed-input
# WMBT: wmbt:define-plans:C001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C001-UNIT-002 — sources list in --json output matches parsed sources."""
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


def test_json_sources_reflect_parsed_input():
    result = _run_plan("docs/spec.md", "--text", "note", "--json")
    assert result.returncode == 0, f"Command failed: {result.stderr}"

    data = json.loads(result.stderr)
    sources = data["sources"]
    assert len(sources) == 2, f"Expected 2 sources, got {len(sources)}: {sources}"

    types = {s["type"] for s in sources}
    assert "file" in types
    assert "text" in types
