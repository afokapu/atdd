# URN: test:author-plan-substrate:author-train:E004-UNIT-001-registry-insert-and-per-train-file
# Acceptance: acc:author-plan-substrate:E004-UNIT-001-registry-insert-and-per-train-file
# WMBT: wmbt:author-plan-substrate:E004
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-001 (plan train) — create_train dedup-inserts into _trains.yaml and writes the per-train file.

RED: create_train does not exist yet.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.planner.commands.author import create_train


def test_create_train_registers_and_writes_per_train_file(tmp_path):
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    spec = {"train_id": "0009-demo-train", "wagons": ["demo-wagon"],
            "description": "a demo train for the writer test"}
    per_train = create_train(spec, root=tmp_path)
    assert per_train == plan / "_trains" / "0009-demo-train.yaml"
    assert per_train.exists()
    registry = yaml.safe_load((plan / "_trains.yaml").read_text())
    assert "0009-demo-train" in yaml.safe_dump(registry)
