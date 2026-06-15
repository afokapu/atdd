# URN: test:author-atdd-substrate:author-scope:E003-SMOKE-001-scope-written-and-sorted
# Acceptance: acc:author-atdd-substrate:E003-SMOKE-001-scope-written-and-sorted
# WMBT: wmbt:author-atdd-substrate:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E003-SMOKE-001 — the real CLI writes a scope into scopes.yaml in sorted position."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

_SRC = Path(__file__).resolve().parents[4]


def _scope(path, sid, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "scope",
         "--scope-id", sid, "--artifact-kind", "source_file", "--runtime", "python",
         "--selector", "path_glob=src/**/*.py", "--path", str(path)],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )


def test_cli_writes_scope_sorted(tmp_path):
    reg = tmp_path / "scopes.yaml"
    assert _scope(reg, "scope.source.zzz", tmp_path).returncode == 0
    assert _scope(reg, "scope.source.aaa", tmp_path).returncode == 0
    doc = yaml.safe_load(reg.read_text())
    assert [s["scope_id"] for s in doc["scopes"]] == ["scope.source.aaa", "scope.source.zzz"]
