# URN: test:author-atdd-substrate:author-gate:E004-SMOKE-001-cli-writes-valid-gate
# Acceptance: acc:author-atdd-substrate:E004-SMOKE-001-cli-writes-valid-gate
# WMBT: wmbt:author-atdd-substrate:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E004-SMOKE-001 — the real CLI writes a schema-valid gate into its per-trigger file."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from atdd.planner.commands.author_registry import validate_gate

_SRC = Path(__file__).resolve().parents[4]


def _gate(path, gid, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "gate",
         "--gate-id", gid, "--trigger-type", "git_hook", "--trigger-name", "post-commit",
         "--selection", "blast_radius", "--action", "never_block",
         "--success-code", "0", "--failure-code", "0", "--path", str(path)],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )


def test_cli_writes_valid_gate_sorted(tmp_path):
    reg = tmp_path / "post-commit.yaml"
    assert _gate(reg, "gate.post_commit.zzz", tmp_path).returncode == 0
    assert _gate(reg, "gate.post_commit.aaa", tmp_path).returncode == 0
    doc = yaml.safe_load(reg.read_text())
    assert [g["gate_id"] for g in doc["gates"]] == ["gate.post_commit.aaa", "gate.post_commit.zzz"]
    for g in doc["gates"]:
        validate_gate(g)  # each authored gate is schema-valid
