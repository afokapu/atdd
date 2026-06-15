# URN: test:author-atdd-substrate:author-gate:C005-UNIT-001-rejects-bad-id-trigger-strategy
# Acceptance: acc:author-atdd-substrate:C005-UNIT-001-rejects-bad-id-trigger-strategy
# WMBT: wmbt:author-atdd-substrate:C005
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C005-UNIT-001 — validate_gate rejects bad gate_id, trigger, and selection strategy."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_registry import validate_gate


def _gate(**over):
    g = {
        "gate_id": "gate.post_commit.x",
        "trigger": {"type": "git_hook", "name": "post-commit"},
        "selection": {"strategy": "blast_radius"},
        "on_violation": {"action": "never_block"},
        "exit": {"success_code": 0, "failure_code": 0},
    }
    g.update(over)
    return g


def test_rejects_bad_gate_id():
    with pytest.raises(AuthorInputError) as exc:
        validate_gate(_gate(gate_id="Bad Gate"))
    assert exc.value.field == "gate_id"


def test_rejects_bad_trigger():
    with pytest.raises(AuthorInputError) as exc:
        validate_gate(_gate(trigger={"type": "nope", "name": "post-commit"}))
    assert exc.value.field == "trigger"


def test_rejects_bad_selection_strategy():
    with pytest.raises(AuthorInputError) as exc:
        validate_gate(_gate(selection={"strategy": "nope"}))
    assert exc.value.field == "selection"
