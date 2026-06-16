# URN: test:author-atdd-substrate:substrate-spine:C006-SMOKE-001-cli-manifest-roundtrip
# Acceptance: acc:author-atdd-substrate:C006-SMOKE-001-cli-manifest-roundtrip
# WMBT: wmbt:author-atdd-substrate:C006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C006-SMOKE-001 — a manifest written by the real CLI passes the manifest validator; an incompatible contract is refused."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from atdd.planner.commands.author_manifest import (
    implementation_accepted_by,
    validate_workspace_manifest,
)

_SRC = Path(__file__).resolve().parents[4]


def _cli(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60)


def test_cli_written_manifest_validates_and_contract_enforced(tmp_path):
    # the real CLI scaffolds a provider; its manifest must pass the validator
    res = _cli(["workspace", "init", "--workspace", "acme.workspace.python-pytest"], tmp_path)
    assert res.returncode == 0, res.stderr
    manifest = yaml.safe_load(
        (tmp_path / "workspaces/acme.workspace.python-pytest/atdd.workspace.yaml").read_text()
    )
    validate_workspace_manifest(manifest)  # round-trip: written-by-construction is valid

    # the contract is enforced against that real provider manifest
    assert implementation_accepted_by({"contract_version": "1.0.0"}, manifest) is True
    assert implementation_accepted_by({"contract_version": "2.0.0"}, manifest) is False
