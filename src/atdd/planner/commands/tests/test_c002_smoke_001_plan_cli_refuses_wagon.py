# URN: test:author-plan-substrate:author-wagon:C002-SMOKE-001-cli-refuses-invalid-wagon
# Acceptance: acc:author-plan-substrate:C002-SMOKE-001-cli-refuses-invalid-wagon
# WMBT: wmbt:author-plan-substrate:C002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C002-SMOKE-001 — the real `atdd author wagon` CLI refuses a structurally invalid wagon."""
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


def test_cli_refuses_wagon_missing_required_field(tmp_path):
    spec = tmp_path / "w.yaml"
    spec.write_text(yaml.safe_dump({
        "wagon": "bad-demo",
        "description": "missing the goal field on purpose here",
        "subject": "agent:planner", "context": "x", "action": "y",
        "outcome": "z", "produce": [{"name": "commons:demo:thing"}],
    }), encoding="utf-8")
    r = _cli(["wagon", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode != 0
    assert not (tmp_path / "plan" / "bad_demo" / "_bad_demo.yaml").exists()
