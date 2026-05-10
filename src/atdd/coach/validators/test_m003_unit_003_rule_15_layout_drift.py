# URN: component:observe-and-correct:observer-runtime-and-rules:test_m003_unit_003_rule_15_layout_drift:backend:domain
# Runtime: python
# Purpose: Reverse-coherence binding for coach.observer.layout-drift (rule 15).

"""Validator wrapper for observer rule 15 (issue #513).

Binds ``coach.observer.layout-drift`` and asserts the absorption-pattern
parity between the rule and ``babysit.correct_layout_drift`` per spec §0.2.
Detailed parity tests live at
``src/atdd/coach/commands/tests/test_m003_unit_003_rule_15_layout_drift.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.commands import babysit, observer
from atdd.coach.observer_rules import layout_drift
from atdd.coach.utils import session_naming
from atdd.coach.utils.rule_binding import bind_rule


_RULE = bind_rule("coach.observer.layout-drift")


pytestmark = [pytest.mark.coach]


def test_rule_15_parity_with_correct_layout_drift(tmp_path: Path):
    """Rule 15 detects layout band changes via target_grid_label and
    re-applies via correct_layout_drift, logging coach.orchestration.layout-conformance."""
    assert _RULE.rule_id == "coach.observer.layout-drift"

    # Absorption: verbatim helpers per spec §0.2.
    assert layout_drift.correct_layout_drift is babysit.correct_layout_drift
    assert layout_drift.target_grid_label is session_naming.target_grid_label

    drifted_ctx = observer.ObservedInput(
        agent_id="agent-A",
        events=(
            {"type": "layout_state", "surface_count": 4, "last_target": ""},
        ),
    )
    target_for_two = session_naming.target_grid_label(2)
    conforming_ctx = observer.ObservedInput(
        agent_id="agent-A",
        events=(
            {"type": "layout_state", "surface_count": 2, "last_target": target_for_two},
        ),
    )
    assert layout_drift.predicate(drifted_ctx) is True
    assert layout_drift.predicate(conforming_ctx) is False

    log_path = tmp_path / "orchestration-log.jsonl"
    layout_cache: dict[str, str] = {}
    fired = layout_drift.apply_correction(
        drifted_ctx, log_path=log_path, layout_cache=layout_cache,
    )
    assert fired is True
    events = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        e.get("rule_id") == "coach.orchestration.layout-conformance"
        for e in events
    )
