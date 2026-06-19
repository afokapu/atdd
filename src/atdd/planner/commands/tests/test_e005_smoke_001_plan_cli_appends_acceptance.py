# URN: test:author-plan-substrate:author-acceptance:E005-SMOKE-001-cli-appends-acceptance
# Acceptance: acc:author-plan-substrate:E005-SMOKE-001-cli-appends-acceptance
# WMBT: wmbt:author-plan-substrate:E005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E005-SMOKE-001 — the real `atdd author acceptance` CLI appends a block into an existing WMBT."""
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


def test_cli_appends_acceptance_to_existing_wmbt(tmp_path):
    # seed a WMBT via the real CLI first
    wspec = tmp_path / "wmbt.yaml"
    wspec.write_text(yaml.safe_dump({
        "wagon_slug": "smoke-demo", "code": "E001",
        "step": "execute", "direction": "maximize", "dimension": "likelihood",
        "object_of_control": "thing-creation", "context_clarifier": "when doing the thing",
        "lens": "functional.effectiveness",
        "statement": "maximize likelihood of thing-creation",
    }), encoding="utf-8")
    assert _cli(["wmbt", "--spec", str(wspec), "--root", str(tmp_path)], tmp_path).returncode == 0

    block = tmp_path / "acc.yaml"
    block.write_text(yaml.safe_dump({
        "identity": {"urn": "acc:smoke-demo:E001-UNIT-001-x", "id": "AC-UNIT-001",
                     "purpose": "an appended acceptance", "phase": "GREEN"},
        "harness": {"type": "unit", "category": "backend"},
        "given": {"abstract": ["a"]}, "when": {"abstract": "b"}, "then": {"abstract": ["c"]},
    }), encoding="utf-8")
    r = _cli(["acceptance", "--wmbt", "wmbt:smoke-demo:E001", "--spec", str(block),
              "--root", str(tmp_path)], tmp_path)
    assert r.returncode == 0, r.stderr
    doc = yaml.safe_load((tmp_path / "plan" / "smoke_demo" / "E001.yaml").read_text())
    urns = [a["identity"]["urn"] for a in doc["acceptances"]]
    assert "acc:smoke-demo:E001-UNIT-001-x" in urns
