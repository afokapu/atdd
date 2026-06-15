# URN: test:author-atdd-substrate:author-gate:E004-UNIT-002-idempotent-atomic
# Acceptance: acc:author-atdd-substrate:E004-UNIT-002-idempotent-atomic
# WMBT: wmbt:author-atdd-substrate:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-002 — re-inserting an identical gate entry is a no-op (atomic)."""
from __future__ import annotations

import yaml

from atdd.planner.commands.author_registry import insert_gate


def _gate():
    return {
        "gate_id": "gate.post_commit.local_feedback", "kind": "gate", "status": "active",
        "trigger": {"type": "git_hook", "name": "post-commit"},
        "selection": {"strategy": "blast_radius"},
        "on_violation": {"action": "never_block"},
        "exit": {"success_code": 0, "failure_code": 0},
    }


def test_reinsert_gate_noop(tmp_path):
    path = tmp_path / "post-commit.yaml"
    insert_gate(_gate(), path)
    first = path.read_text()
    insert_gate(_gate(), path)
    second = path.read_text()
    assert first == second
    assert len(yaml.safe_load(second)["gates"]) == 1
