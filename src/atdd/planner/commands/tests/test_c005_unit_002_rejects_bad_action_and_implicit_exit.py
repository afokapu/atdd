# URN: test:author-atdd-substrate:author-gate:C005-UNIT-002-rejects-bad-action-and-implicit-exit
# Acceptance: acc:author-atdd-substrate:C005-UNIT-002-rejects-bad-action-and-implicit-exit
# WMBT: wmbt:author-atdd-substrate:C005
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C005-UNIT-002 — validate_gate rejects a bad action and an implicit (missing) exit."""
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


def test_rejects_bad_action():
    with pytest.raises(AuthorInputError) as exc:
        validate_gate(_gate(on_violation={"action": "explode"}))
    assert exc.value.field == "action"


def test_rejects_implicit_exit():
    g = _gate()
    del g["exit"]  # exit behavior must be explicit
    with pytest.raises(AuthorInputError) as exc:
        validate_gate(g)
    assert exc.value.field == "exit"
