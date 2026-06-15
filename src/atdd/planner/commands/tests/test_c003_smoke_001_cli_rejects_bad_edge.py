# URN: test:author-atdd-substrate:author-relationship:C003-SMOKE-001-cli-rejects-bad-edge
# Acceptance: acc:author-atdd-substrate:C003-SMOKE-001-cli-rejects-bad-edge
# WMBT: wmbt:author-atdd-substrate:C003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C003-SMOKE-001 — the real CLI rejects a malformed edge, leaves the file untouched."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]


def test_cli_rejects_bad_edge_file_untouched(tmp_path):
    reg = tmp_path / "relationships.yaml"
    # seed a valid registry first
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path)}
    seed = subprocess.run(
        [sys.executable, "-m", "atdd", "author", "relationship",
         "--source", "coder.green.a", "--type", "enables", "--target", "coder.green.b",
         "--path", str(reg)],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=60,
    )
    assert seed.returncode == 0
    before = reg.read_text()

    # now attempt a malformed edge (invalid type)
    bad = subprocess.run(
        [sys.executable, "-m", "atdd", "author", "relationship",
         "--source", "coder.green.a", "--type", "not_a_real_type", "--target", "coder.green.c",
         "--path", str(reg)],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=60,
    )
    assert bad.returncode != 0
    assert "type" in bad.stderr.lower()
    assert reg.read_text() == before, "registry was modified by a rejected edge"
