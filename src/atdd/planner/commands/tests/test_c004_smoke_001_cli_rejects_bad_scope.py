# URN: test:author-atdd-substrate:author-scope:C004-SMOKE-001-cli-rejects-bad-scope
# Acceptance: acc:author-atdd-substrate:C004-SMOKE-001-cli-rejects-bad-scope
# WMBT: wmbt:author-atdd-substrate:C004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C004-SMOKE-001 — the real CLI rejects an empty scope, leaving scopes.yaml untouched."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]


def _run(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "scope", "--core", *args],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )


def test_cli_rejects_empty_scope(tmp_path):
    reg = tmp_path / "scopes.yaml"
    # seed one valid scope
    assert _run(["--scope-id", "scope.source.python", "--selector", "path_glob=src/**/*.py", "--path", str(reg)], tmp_path).returncode == 0
    before = reg.read_text()
    # a scope with zero selectors must be refused
    bad = _run(["--scope-id", "scope.source.empty", "--path", str(reg)], tmp_path)
    assert bad.returncode != 0
    assert "selector" in bad.stderr.lower()
    assert reg.read_text() == before
