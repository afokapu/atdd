# URN: test:author-atdd-substrate:author-scope:C004-SMOKE-001-cli-rejects-bad-scope
# Acceptance: acc:author-atdd-substrate:C004-SMOKE-001-cli-rejects-bad-scope
# WMBT: wmbt:author-atdd-substrate:C004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C004-SMOKE-001 — the real CLI rejects a malformed scope, leaving the file untouched."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]


def _run(extra, cwd, path):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "scope", "--core",
         "--scope-id", "scope.source.python", "--path", str(path), *extra],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )


def test_cli_rejects_bad_selector_type(tmp_path):
    reg = tmp_path / "scope.source.python.scope.yaml"
    # seed a valid scope file
    ok = _run(["--selector-id", "selector.source.python.pg", "--selector-type", "path_glob",
               "--include", "src/**/*.py"], tmp_path, reg)
    assert ok.returncode == 0, ok.stderr
    before = reg.read_text()
    # an invalid selector type must be refused; the seeded scope file stays put
    bad = _run(["--selector-id", "selector.source.python.bad", "--selector-type", "regex",
                "--include", "src/**/*.py"], tmp_path, reg)
    assert bad.returncode != 0
    assert "selector" in bad.stderr.lower()
    assert reg.read_text() == before
