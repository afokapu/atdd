# URN: test:author-atdd-substrate:author-convention-node:E001-UNIT-002-conflict-free-second-rule
# Acceptance: acc:author-atdd-substrate:E001-UNIT-002-conflict-free-second-rule
# WMBT: wmbt:author-atdd-substrate:E001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E001-UNIT-002 — a second rule_id adds a new file without touching the first."""
from __future__ import annotations

from atdd.planner.commands.author import create_convention_node


def test_second_rule_is_conflict_free(tmp_path):
    p1 = create_convention_node(
        role="coder", rule_id="coder.green.component-urn-marker-is",
        statement="A.", terms=[{"term_id": "a", "text": "a"}], root=tmp_path,
    )
    first_bytes = p1.read_bytes()
    p2 = create_convention_node(
        role="coder", rule_id="coder.green.component-urn-matches-pattern",
        statement="B.", terms=[{"term_id": "b", "text": "b"}], root=tmp_path,
    )
    assert p1 != p2
    assert p2.exists()
    # the first file is untouched (per-rule_id files never collide)
    assert p1.read_bytes() == first_bytes
