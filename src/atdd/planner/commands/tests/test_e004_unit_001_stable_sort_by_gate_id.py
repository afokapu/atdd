# URN: test:author-atdd-substrate:author-gate:E004-UNIT-001-stable-sort-by-gate-id
# Acceptance: acc:author-atdd-substrate:E004-UNIT-001-stable-sort-by-gate-id
# WMBT: wmbt:author-atdd-substrate:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-001 — inserting two gate entries yields a per-trigger file sorted by gate_id."""
from __future__ import annotations

import yaml

from atdd.planner.commands.author_registry import insert_gate


def _gate(gid):
    return {
        "gate_id": gid, "kind": "gate", "status": "active",
        "trigger": {"type": "git_hook", "name": "post-commit"},
        "selection": {"strategy": "blast_radius"},
        "on_violation": {"action": "never_block"},
        "exit": {"success_code": 0, "failure_code": 0},
    }


def test_two_gates_sorted(tmp_path):
    path = tmp_path / "post-commit.yaml"
    insert_gate(_gate("gate.post_commit.zzz"), path)
    insert_gate(_gate("gate.post_commit.aaa"), path)
    doc = yaml.safe_load(path.read_text())
    assert [g["gate_id"] for g in doc["gates"]] == ["gate.post_commit.aaa", "gate.post_commit.zzz"]
