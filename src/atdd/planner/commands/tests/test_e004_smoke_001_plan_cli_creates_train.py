# URN: test:author-plan-substrate:author-train:E004-SMOKE-001-cli-creates-valid-train
# Acceptance: acc:author-plan-substrate:E004-SMOKE-001-cli-creates-valid-train
# WMBT: wmbt:author-plan-substrate:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E004-SMOKE-001 — the real `atdd author train` CLI registers a train + per-train file."""
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


def test_cli_registers_train_and_writes_per_train_file(tmp_path):
    (tmp_path / "plan" / "_trains").mkdir(parents=True)
    (tmp_path / "plan" / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    spec = tmp_path / "train.yaml"
    spec.write_text(yaml.safe_dump({
        "train_id": "0009-smoke-demo-train",
        "wagons": ["smoke-demo"],
        "description": "a smoke demo train authored via the real CLI",
    }), encoding="utf-8")
    r = _cli(["train", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "plan" / "_trains" / "0009-smoke-demo-train.yaml").exists()
    assert "0009-smoke-demo-train" in (tmp_path / "plan" / "_trains.yaml").read_text()
