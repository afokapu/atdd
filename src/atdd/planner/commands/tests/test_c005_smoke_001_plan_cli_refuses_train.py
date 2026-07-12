# URN: test:author-plan-substrate:author-train:C005-SMOKE-001-cli-refuses-invalid-train
# Acceptance: acc:author-plan-substrate:C005-SMOKE-001-cli-refuses-invalid-train
# WMBT: wmbt:author-plan-substrate:C005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C005-SMOKE-001 — the real `atdd author train` CLI refuses a malformed train_id, registry intact."""
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


def test_cli_refuses_malformed_train_id_registry_unchanged(tmp_path):
    (tmp_path / "plan" / "_trains").mkdir(parents=True)
    reg = tmp_path / "plan" / "_trains.yaml"
    reg.write_text("trains: {}\n", encoding="utf-8")
    before = reg.read_text()
    spec = tmp_path / "t.yaml"
    spec.write_text(yaml.safe_dump({
        "train_id": "Not A Train Id", "wagons": ["demo-wagon"], "description": "x",
    }), encoding="utf-8")
    r = _cli(["train", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode != 0
    assert reg.read_text() == before
