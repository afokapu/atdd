# URN: test:author-atdd-substrate:substrate-spine:P002-SMOKE-001-cli-init
# Acceptance: acc:author-atdd-substrate:P002-SMOKE-001-cli-init
# WMBT: wmbt:author-atdd-substrate:P002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""P002-SMOKE-001 — the real CLI scaffolds extension and workspace packages on disk."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]


def _cli(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60)


def test_cli_workspace_and_extension_init(tmp_path):
    # workspace init → first-class provider package
    ws = _cli(["workspace", "init", "--workspace", "acme.workspace.python-pytest"], tmp_path)
    assert ws.returncode == 0, ws.stderr
    assert (tmp_path / "workspaces/acme.workspace.python-pytest/atdd.workspace.yaml").exists()

    # extension init → use-case package
    ext = _cli(["extension", "init", "--extension", "acme.extension.component-header-validator"], tmp_path)
    assert ext.returncode == 0, ext.stderr
    assert (tmp_path / "extensions/acme.extension.component-header-validator/atdd.extension.yaml").exists()

    # a reserved-publisher workspace id is refused, nothing written
    bad = _cli(["workspace", "init", "--workspace", "atdd.workspace.python-pytest"], tmp_path)
    assert bad.returncode != 0
    assert "reserved" in bad.stderr.lower()
    assert not (tmp_path / "workspaces/atdd.workspace.python-pytest").exists()
