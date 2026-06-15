# URN: test:author-atdd-substrate:author-convention-node:C002-SMOKE-001-cli-rejects-bad-node
# Acceptance: acc:author-atdd-substrate:C002-SMOKE-001-cli-rejects-bad-node
# WMBT: wmbt:author-atdd-substrate:C002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C002-SMOKE-001 — the real CLI rejects a structurally invalid node, writes nothing."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]


def _run(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "convention-node", *args],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )


def test_cli_rejects_numbered_term(tmp_path):
    result = _run(
        [
            "--role", "coder", "--rule-id", "coder.green.bad",
            "--statement", "x",
            "--term", "T1=numbered ids are forbidden",
        ],
        tmp_path,
    )
    assert result.returncode != 0
    assert "term" in result.stderr.lower()
    assert not (tmp_path / "src").exists(), "CLI wrote an artifact for an invalid node"
