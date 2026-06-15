# URN: test:author-atdd-substrate:author-relationship:E002-UNIT-002-idempotent-reinsert
# Acceptance: acc:author-atdd-substrate:E002-UNIT-002-idempotent-reinsert
# WMBT: wmbt:author-atdd-substrate:E002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E002-UNIT-002 — re-inserting an identical edge is a no-op (dedup), atomic write."""
from __future__ import annotations

import yaml

from atdd.planner.commands.author_registry import insert_relationship


def _edge():
    return {
        "source_ref": "coder.green.a", "type": "enables", "target_ref": "coder.green.b",
        "foundation": "finish_to_start", "constraint": "mandatory",
        "control": "internal", "strength": "critical", "reason": "x", "confidence": 1.0,
    }


def test_reinsert_is_noop(tmp_path):
    path = tmp_path / "relationships.yaml"
    insert_relationship(_edge(), path)
    first = path.read_text()
    insert_relationship(_edge(), path)  # identical edge again
    second = path.read_text()
    doc = yaml.safe_load(second)
    assert len(doc["edges"]) == 1, "duplicate edge was not deduplicated"
    assert first == second, "re-insert was not byte-idempotent"
