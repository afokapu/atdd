# URN: test:author-atdd-substrate:author-gate:C005-SMOKE-001-cli-rejects-bad-gate
# Acceptance: acc:author-atdd-substrate:C005-SMOKE-001-cli-rejects-bad-gate
# WMBT: wmbt:author-atdd-substrate:C005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C005-SMOKE-001 — the real CLI rejects a malformed gate, leaving the file untouched."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]


def _run(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "gate", *args],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )


def test_cli_rejects_bad_gate(tmp_path):
    reg = tmp_path / "post-commit.yaml"
    base = ["--trigger-type", "git_hook", "--trigger-name", "post-commit",
            "--selection", "blast_radius", "--action", "never_block", "--path", str(reg)]
    assert _run(["--gate-id", "gate.post_commit.ok", *base], tmp_path).returncode == 0
    before = reg.read_text()
    # invalid violation action
    bad = _run(["--gate-id", "gate.post_commit.bad", "--trigger-type", "git_hook",
                "--trigger-name", "post-commit", "--selection", "blast_radius",
                "--action", "explode", "--path", str(reg)], tmp_path)
    assert bad.returncode != 0
    assert "action" in bad.stderr.lower()
    assert reg.read_text() == before
