# URN: test:author-atdd-substrate:author-relationship:E002-SMOKE-001-two-edges-sorted-deduped
# Acceptance: acc:author-atdd-substrate:E002-SMOKE-001-two-edges-sorted-deduped
# WMBT: wmbt:author-atdd-substrate:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E002-SMOKE-001 — the real CLI inserts two edges, sorted + deduped."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

_SRC = Path(__file__).resolve().parents[4]


def _author_rel(path, source, target, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run(
        [
            sys.executable, "-m", "atdd", "author", "relationship",
            "--source", source, "--type", "enables", "--target", target,
            "--path", str(path),
        ],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )


def test_cli_inserts_two_edges_sorted_deduped(tmp_path):
    reg = tmp_path / "relationships.yaml"
    assert _author_rel(reg, "coder.green.zzz", "coder.green.t", tmp_path).returncode == 0
    assert _author_rel(reg, "coder.green.aaa", "coder.green.t", tmp_path).returncode == 0
    # re-insert the first edge — must dedup
    assert _author_rel(reg, "coder.green.zzz", "coder.green.t", tmp_path).returncode == 0
    doc = yaml.safe_load(reg.read_text())
    sources = [e["source_ref"] for e in doc["edges"]]
    assert sources == ["coder.green.aaa", "coder.green.zzz"], sources
