# URN: test:author-atdd-substrate:author-scope:E003-SMOKE-001-scope-written-and-sorted
# Acceptance: acc:author-atdd-substrate:E003-SMOKE-001-scope-written-and-sorted
# WMBT: wmbt:author-atdd-substrate:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E003-SMOKE-001 — the real CLI writes a per-file scope with selectors sorted by selector_id."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

_SRC = Path(__file__).resolve().parents[4]


def _scope(path, selector_id, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "scope", "--core",
         "--scope-id", "scope.source.python", "--artifact-kind", "source_file", "--runtime", "python",
         "--selector-id", selector_id, "--selector-type", "path_glob",
         "--include", "src/**/*.py", "--exclude", ".venv/**", "--path", str(path)],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )


def test_cli_writes_scope_with_sorted_selectors(tmp_path):
    reg = tmp_path / "scope.source.python.scope.yaml"
    assert _scope(reg, "selector.source.python.zzz", tmp_path).returncode == 0
    assert _scope(reg, "selector.source.python.aaa", tmp_path).returncode == 0
    doc = yaml.safe_load(reg.read_text())
    assert doc["scope_id"] == "scope.source.python"
    assert [s["selector_id"] for s in doc["selectors"]] == [
        "selector.source.python.aaa", "selector.source.python.zzz"]
    assert doc["selectors"][0]["include"] == ["src/**/*.py"]
