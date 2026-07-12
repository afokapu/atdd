# URN: test:author-plan-substrate:author-plan-spine:C001-SMOKE-001-cli-refuses-bad-plan-input
# Acceptance: acc:author-plan-substrate:C001-SMOKE-001-cli-refuses-bad-plan-input
# WMBT: wmbt:author-plan-substrate:C001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C001-SMOKE-001 — the real CLI exits non-zero and writes nothing for invalid plan input."""
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


def test_cli_refuses_non_kebab_slug_and_writes_nothing(tmp_path):
    spec = tmp_path / "wagon.yaml"
    spec.write_text(yaml.safe_dump({
        "wagon": "Not_Kebab",
        "description": "a wagon with an invalid slug on purpose",
        "subject": "agent:planner", "context": "x", "action": "y",
        "goal": "z", "outcome": "w", "produce": [{"name": "commons:demo:thing"}],
    }), encoding="utf-8")
    r = _cli(["wagon", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode != 0
    assert not (tmp_path / "plan").exists()
