# URN: test:author-plan-substrate:author-wmbt:C004-SMOKE-001-cli-refuses-invalid-wmbt
# Acceptance: acc:author-plan-substrate:C004-SMOKE-001-cli-refuses-invalid-wmbt
# WMBT: wmbt:author-plan-substrate:C004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C004-SMOKE-001 — the real `atdd author wmbt` CLI refuses a WMBT whose statement omits its OOC."""
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


def test_cli_refuses_wmbt_statement_without_ooc(tmp_path):
    spec = tmp_path / "m.yaml"
    spec.write_text(yaml.safe_dump({
        "wagon_slug": "demo-wagon", "code": "E001",
        "step": "execute", "direction": "maximize", "dimension": "likelihood",
        "object_of_control": "thing-creation", "context_clarifier": "when doing the thing",
        "lens": "functional.effectiveness",
        "statement": "maximize likelihood of something unrelated",  # omits 'thing-creation'
    }), encoding="utf-8")
    r = _cli(["wmbt", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode != 0
    assert not (tmp_path / "plan" / "demo_wagon" / "E001.yaml").exists()
