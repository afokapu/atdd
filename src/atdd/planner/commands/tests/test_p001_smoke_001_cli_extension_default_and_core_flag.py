# URN: test:author-atdd-substrate:substrate-spine:P001-SMOKE-001-cli-extension-default-and-core-flag
# Acceptance: acc:author-atdd-substrate:P001-SMOKE-001-cli-extension-default-and-core-flag
# WMBT: wmbt:author-atdd-substrate:P001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""P001-SMOKE-001 — the real CLI is extension-first: extension by default, core only with --core."""
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


def test_extension_is_default_and_core_is_protected(tmp_path):
    # 1. --extension → writes inside the extension package, NOT into src/atdd/
    ext = _cli(["convention-node", "--extension", "bromohub.extension.component-header-validator",
                "--rule-id", "coder.source.component-header-required",
                "--statement", "s", "--term", "t=y"], tmp_path)
    assert ext.returncode == 0, ext.stderr
    ext_file = tmp_path / "extensions/bromohub.extension.component-header-validator/conventions/coder.source.component-header-required.convention.yaml"
    assert ext_file.exists(), ext.stdout + ext.stderr
    assert not (tmp_path / "src").exists(), "extension authoring leaked into core src/atdd/"

    # 2. --core → writes into the core protocol path
    core = _cli(["convention-node", "--core", "--role", "coach",
                 "--rule-id", "coach.extension.manifest-has-owner-boundary",
                 "--statement", "s", "--term", "t=y"], tmp_path)
    assert core.returncode == 0, core.stderr
    assert (tmp_path / "src/atdd/coach/conventions/nodes/coach.extension.manifest-has-owner-boundary.convention.yaml").exists()

    # 3. neither flag, no extension context → refused, nothing written
    none = _cli(["convention-node", "--rule-id", "coder.source.x", "--statement", "s", "--term", "t=y"],
                tmp_path)
    assert none.returncode != 0
    assert "context" in none.stderr.lower()
