# URN: test:author-plan-substrate:author-wmbt:E003-SMOKE-001-cli-creates-valid-wmbt
# Acceptance: acc:author-plan-substrate:E003-SMOKE-001-cli-creates-valid-wmbt
# WMBT: wmbt:author-plan-substrate:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E003-SMOKE-001 — the real `atdd author wmbt` CLI writes an ODI WMBT with a SMOKE acceptance."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

_SRC = Path(__file__).resolve().parents[4]


def _cli(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60)


def test_cli_creates_wmbt_with_seed_smoke(tmp_path):
    spec = tmp_path / "wmbt.yaml"
    spec.write_text(yaml.safe_dump({
        "wagon_slug": "smoke-demo", "code": "E001",
        "step": "execute", "direction": "maximize", "dimension": "likelihood",
        "object_of_control": "thing-creation",
        "context_clarifier": "when doing the thing, the writer creates a file",
        "lens": "functional.effectiveness",
        "statement": "maximize likelihood of thing-creation when authoring the thing",
    }), encoding="utf-8")
    r = _cli(["wmbt", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode == 0, r.stderr
    wmbt = tmp_path / "plan" / "smoke_demo" / "E001.yaml"
    assert wmbt.exists()
    doc = yaml.safe_load(wmbt.read_text())
    assert "SMOKE" in [a["identity"]["phase"] for a in doc["acceptances"]]
