# URN: test:author-plan-substrate:author-feature:C003-SMOKE-001-cli-refuses-invalid-feature
# Acceptance: acc:author-plan-substrate:C003-SMOKE-001-cli-refuses-invalid-feature
# WMBT: wmbt:author-plan-substrate:C003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C003-SMOKE-001 — the real `atdd author feature` CLI refuses a structurally invalid feature."""
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


def test_cli_refuses_feature_missing_sizing(tmp_path):
    spec = tmp_path / "f.yaml"
    spec.write_text(yaml.safe_dump({
        "urn": "feature:demo-wagon:do-thing",
        "wagon": "wagon:demo-wagon",
        "description": "a feature missing its sizing block on purpose",
        "wmbts": ["wmbt:demo-wagon:E001"],
        "components": {"backend": {"application": [
            {"type": "use_cases", "count": 1, "rationale": "the demo write path here"}]}},
    }), encoding="utf-8")
    r = _cli(["feature", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode != 0
    assert not (tmp_path / "plan" / "demo_wagon" / "features" / "do_thing.yaml").exists()
