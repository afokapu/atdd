# URN: test:observe-and-correct:observer-runtime-and-rules:M003-UNIT-003-rule-15-layout-drift
# Acceptance: acc:observe-and-correct:M003-UNIT-003-rule-15-layout-drift
# WMBT: wmbt:observe-and-correct:M003
# Phase: RED
# Layer: application
"""M003-UNIT-003 — Rule `coach.observer.layout-drift` (rule 15).

Per spec §0.2 / §8.3, the rule absorbs ``babysit.correct_layout_drift``
into the observer substrate. The rule must:

  * detect a surface count or arrangement that no longer matches
    ``session_naming.target_grid_label``
  * call ``correct_layout_drift`` to re-apply the canonical layout
  * log ``coach.orchestration.layout-conformance``
  * NOT fire on conforming arrangements

Issue #513 (L4). Spec: ``atdd-coach-spec-v9.md`` §8.3.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest

from atdd.coach.commands import observer
from atdd.coach.commands._archived import babysit
from atdd.coach.utils import session_naming

pytestmark = [pytest.mark.platform]


def _read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_rule_15_module_exposes_build_rule_and_predicate():
    from atdd.coach.observer_rules import layout_drift

    assert callable(layout_drift.build_rule)
    assert callable(layout_drift.predicate)
    # Absorbed verbatim per spec §0.2:
    assert layout_drift.correct_layout_drift is babysit.correct_layout_drift
    assert layout_drift.target_grid_label is session_naming.target_grid_label


def test_rule_15_build_rule_binds_canonical_rule_id():
    from atdd.coach.observer_rules import layout_drift

    rule = layout_drift.build_rule()
    assert isinstance(rule, observer.ObserverRule)
    assert rule.rule_id == "coach.observer.layout-drift"


# ---------------------------------------------------------------------------
# Predicate semantics
# ---------------------------------------------------------------------------


def test_rule_15_predicate_fires_on_layout_band_change():
    """A change in surface count that crosses a target_grid_label band fires the rule."""
    from atdd.coach.observer_rules import layout_drift

    # 3 surfaces → "shell (left) + 2x2 grid (right region)" — different from
    # the prior "1 surface" band.
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        events=(
            {"type": "layout_state", "surface_count": 3, "last_target": "shell (left) + 1 surface (right)"},
        ),
    )
    assert layout_drift.predicate(ctx) is True


def test_rule_15_predicate_silent_when_already_conforming():
    """When ``last_target`` already matches the current surface count, no fire."""
    from atdd.coach.observer_rules import layout_drift

    target_for_three = session_naming.target_grid_label(3)
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        events=(
            {"type": "layout_state", "surface_count": 3, "last_target": target_for_three},
        ),
    )
    assert layout_drift.predicate(ctx) is False


def test_rule_15_predicate_silent_when_no_layout_state_events():
    from atdd.coach.observer_rules import layout_drift

    ctx = observer.ObservedInput(agent_id="agent-A")
    assert layout_drift.predicate(ctx) is False


# ---------------------------------------------------------------------------
# Parity with babysit.correct_layout_drift — re-applies + logs
# ---------------------------------------------------------------------------


def test_rule_15_apply_correction_re_applies_layout_and_logs(tmp_path: Path):
    """``apply_correction(ctx, log_path, layout_cache)`` must call
    babysit.correct_layout_drift, which logs the structured
    ``coach.orchestration.layout-conformance`` event."""
    from atdd.coach.observer_rules import layout_drift

    log_path = tmp_path / "orchestration-log.jsonl"
    layout_cache: Dict[str, str] = {}

    ctx = observer.ObservedInput(
        agent_id="agent-A",
        events=(
            {"type": "layout_state", "surface_count": 4, "last_target": ""},
        ),
    )
    fired = layout_drift.apply_correction(
        ctx, log_path=log_path, layout_cache=layout_cache,
    )
    assert fired is True

    events = _read_jsonl(log_path)
    rule_id_events = [
        e for e in events if e.get("rule_id") == "coach.orchestration.layout-conformance"
    ]
    assert rule_id_events, (
        "rule 15 must log coach.orchestration.layout-conformance"
    )
    # The layout_cache must remember the applied target — second call is a no-op.
    fired_again = layout_drift.apply_correction(
        ctx, log_path=log_path, layout_cache=layout_cache,
    )
    assert fired_again is False, (
        "correct_layout_drift is idempotent — same band must not re-log"
    )


def test_rule_15_apply_correction_idempotent_on_conforming_layout(tmp_path: Path):
    from atdd.coach.observer_rules import layout_drift

    log_path = tmp_path / "orchestration-log.jsonl"
    target = session_naming.target_grid_label(2)
    # When the cache already records the correct target, no work needed.
    layout_cache: Dict[str, str] = {"last_target": target}

    ctx = observer.ObservedInput(
        agent_id="agent-A",
        events=(
            {"type": "layout_state", "surface_count": 2, "last_target": target},
        ),
    )
    fired = layout_drift.apply_correction(
        ctx, log_path=log_path, layout_cache=layout_cache,
    )
    assert fired is False
    assert _read_jsonl(log_path) == []
