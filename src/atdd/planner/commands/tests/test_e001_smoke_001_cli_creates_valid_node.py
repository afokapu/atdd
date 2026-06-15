# URN: test:author-atdd-substrate:author-convention-node:E001-SMOKE-001-cli-creates-valid-node
# Acceptance: acc:author-atdd-substrate:E001-SMOKE-001-cli-creates-valid-node
# WMBT: wmbt:author-atdd-substrate:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E001-SMOKE-001 — the real CLI writes a schema-valid flat per-role node."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from atdd.planner.commands.author import validate_convention_node

_SRC = Path(__file__).resolve().parents[4]


def test_cli_creates_schema_valid_node(tmp_path):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path)}
    result = subprocess.run(
        [
            sys.executable, "-m", "atdd", "author", "convention-node",
            "--role", "coder",
            "--rule-id", "coder.green.component-urn-marker-is",
            "--statement", "Implementation files must declare the component URN marker.",
            "--term", "urn_marker=Every implementation file declares a component URN marker.",
        ],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    path = tmp_path / "src" / "atdd" / "coder" / "conventions" / "nodes" / "coder.green.component-urn-marker-is.convention.yaml"
    assert path.exists(), f"node not created\n{result.stderr}"
    node = yaml.safe_load(path.read_text())
    # the real artifact validates against the canonical convention-node schema
    validate_convention_node(node, path)
    assert node["rule_id"] == "coder.green.component-urn-marker-is"
