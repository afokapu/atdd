# URN: test:author-plan-substrate:author-wagon:E001-SMOKE-001-cli-creates-valid-wagon
# Acceptance: acc:author-plan-substrate:E001-SMOKE-001-cli-creates-valid-wagon
# WMBT: wmbt:author-plan-substrate:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E001-SMOKE-001 — the real `atdd author wagon` CLI writes a schema-valid manifest."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import validate

_SRC = Path(__file__).resolve().parents[4]
_PLAN_SCHEMAS = _SRC / "atdd" / "planner" / "schemas"


def _cli(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60)


def test_cli_creates_schema_valid_wagon(tmp_path):
    spec = tmp_path / "wagon.yaml"
    spec.write_text(yaml.safe_dump({
        "wagon": "smoke-demo",
        "description": "a smoke demo wagon authored via the real CLI",
        "subject": "agent:planner", "context": "smoke", "action": "writes",
        "goal": "prove the CLI works", "outcome": "a manifest exists",
        "produce": [{"name": "commons:demo:thing"}],
    }), encoding="utf-8")
    r = _cli(["wagon", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode == 0, r.stderr
    manifest = tmp_path / "plan" / "smoke_demo" / "_smoke_demo.yaml"
    assert manifest.exists()
    validate(yaml.safe_load(manifest.read_text()),
             json.loads((_PLAN_SCHEMAS / "wagon.schema.json").read_text()))
