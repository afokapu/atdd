# URN: test:author-plan-substrate:author-acceptance:C006-SMOKE-001-cli-refuses-malformed-acceptance
# Acceptance: acc:author-plan-substrate:C006-SMOKE-001-cli-refuses-malformed-acceptance
# WMBT: wmbt:author-plan-substrate:C006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C006-SMOKE-001 — the real `atdd author acceptance` CLI refuses a non-existent target WMBT."""
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


def test_cli_refuses_acceptance_for_missing_wmbt(tmp_path):
    (tmp_path / "plan").mkdir()
    block = tmp_path / "a.yaml"
    block.write_text(yaml.safe_dump({
        "identity": {"urn": "acc:demo-wagon:E001-UNIT-001-x", "id": "AC-UNIT-001",
                     "purpose": "x", "phase": "GREEN"},
        "harness": {"type": "unit", "category": "backend"},
        "given": {"abstract": ["a"]}, "when": {"abstract": "b"}, "then": {"abstract": ["c"]},
    }), encoding="utf-8")
    r = _cli(["acceptance", "--wmbt", "wmbt:demo-wagon:NOPE", "--spec", str(block),
              "--root", str(tmp_path)], tmp_path)
    assert r.returncode != 0
