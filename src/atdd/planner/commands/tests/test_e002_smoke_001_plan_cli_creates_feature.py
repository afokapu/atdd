# URN: test:author-plan-substrate:author-feature:E002-SMOKE-001-cli-creates-valid-feature
# Acceptance: acc:author-plan-substrate:E002-SMOKE-001-cli-creates-valid-feature
# WMBT: wmbt:author-plan-substrate:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E002-SMOKE-001 — the real `atdd author feature` CLI writes a schema-valid feature."""
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


def test_cli_creates_schema_valid_feature(tmp_path):
    spec = tmp_path / "feature.yaml"
    spec.write_text(yaml.safe_dump({
        "urn": "feature:smoke-demo:do-thing",
        "wagon": "wagon:smoke-demo",
        "description": "a smoke demo feature authored via the real CLI",
        "sizing": {"wmbts": 1, "footprint_score": 4, "footprint_size": "S"},
        "wmbts": ["wmbt:smoke-demo:E001"],
        "components": {"backend": {"application": [
            {"type": "use_cases", "count": 1, "rationale": "the create_feature write path"}]}},
    }), encoding="utf-8")
    r = _cli(["feature", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode == 0, r.stderr
    feat = tmp_path / "plan" / "smoke_demo" / "features" / "do_thing.yaml"
    assert feat.exists()
    validate(yaml.safe_load(feat.read_text()),
             json.loads((_PLAN_SCHEMAS / "feature.schema.json").read_text()))
