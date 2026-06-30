# URN: test:author-atdd-substrate:author-convention-node:E007-SMOKE-001-cli-writes-validation
# Acceptance: acc:author-atdd-substrate:E007-SMOKE-001-cli-writes-validation
# WMBT: wmbt:author-atdd-substrate:E007
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E007-SMOKE-001 — the real CLI writes a schema-valid node carrying the top-level
`validation` block, and rejects malformed `--validation` JSON before any write."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from atdd.planner.commands.author import validate_convention_node

_SRC = Path(__file__).resolve().parents[4]
_RID = "planner.train.interlocking-projection-equivalence"
_VALIDATION = {
    "family": "coherence",
    "template": "resolved_fact_agreement",
    "subject_kind": "interlocking",
    "phase": "GREEN",
    "enforcement": "strict",
}


def _run(args, tmp_path):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path)}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "convention-node", "--core",
         "--role", "planner", "--rule-id", _RID,
         "--statement", "An interlocking projection must equal its declared route table.",
         "--term", "interlocking=the route-control model for the train domain", *args],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=60,
    )


def _node_path(tmp_path):
    return (tmp_path / "src" / "atdd" / "planner" / "conventions" / "nodes"
            / f"{_RID}.convention.yaml")


def test_cli_writes_node_carrying_validation(tmp_path):
    result = _run(["--validation", json.dumps(_VALIDATION)], tmp_path)
    assert result.returncode == 0, result.stderr
    path = _node_path(tmp_path)
    assert path.exists(), f"node not created\n{result.stderr}"
    node = yaml.safe_load(path.read_text())
    validate_convention_node(node, path)
    assert node["validation"] == _VALIDATION


def test_cli_rejects_malformed_validation_json(tmp_path):
    result = _run(["--validation", "{not json"], tmp_path)
    assert result.returncode != 0
    assert not _node_path(tmp_path).exists()
