# URN: test:observe-and-correct:observer-runtime-and-rules:M003-UNIT-002-rule-14-canonical-naming-drift
# Acceptance: acc:observe-and-correct:M003-UNIT-002-rule-14-naming-drift
# WMBT: wmbt:observe-and-correct:M003
# Phase: RED
# Layer: application
"""M003-UNIT-002 — Rule `coach.observer.canonical-naming-drift` (rule 14).

Per spec §0.2 / §8.3, the rule absorbs ``babysit.correct_naming_drift``
into the observer substrate. The rule must:

  * detect a multiplexer surface whose name has drifted from canonical
    (per ``session_naming.is_canonical_name``)
  * call ``correct_naming_drift`` to re-apply the canonical name within
    one tick
  * log ``coach.orchestration.canonical-session-name``
  * NOT fire on surfaces already at canonical names

Issue #513 (L4). Spec: ``atdd-coach-spec-v9.md`` §8.3.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from atdd.coach.commands import observer
from atdd.coach.commands._archived import babysit
from atdd.coach.utils import session_naming

pytestmark = [pytest.mark.platform]


class _StubBackend:
    """In-memory MultiplexerBackend stand-in for parity tests."""

    name = "stub"

    def __init__(self) -> None:
        self.renames: List[Tuple[str, str]] = []
        self.sends: List[Tuple[str, str]] = []

    def rename(self, ref: str, new_name: str) -> None:
        self.renames.append((ref, new_name))

    def send(self, ref: str, text: str) -> None:
        self.sends.append((ref, text))


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_rule_14_module_exposes_build_rule_and_predicate():
    from atdd.coach.observer_rules import canonical_naming_drift

    assert callable(canonical_naming_drift.build_rule)
    assert callable(canonical_naming_drift.predicate)
    # Absorbed verbatim per spec §0.2:
    assert canonical_naming_drift.correct_naming_drift is babysit.correct_naming_drift
    assert canonical_naming_drift.is_canonical_name is session_naming.is_canonical_name


def test_rule_14_build_rule_binds_canonical_rule_id():
    from atdd.coach.observer_rules import canonical_naming_drift

    rule = canonical_naming_drift.build_rule()
    assert isinstance(rule, observer.ObserverRule)
    assert rule.rule_id == "coach.observer.canonical-naming-drift"


# ---------------------------------------------------------------------------
# Predicate semantics — drift detection via is_canonical_name
# ---------------------------------------------------------------------------


def test_rule_14_predicate_fires_when_surface_name_drifts():
    """A non-canonical surface name in ctx.events fires the rule."""
    from atdd.coach.observer_rules import canonical_naming_drift

    ctx = observer.ObservedInput(
        agent_id="agent-A",
        events=(
            {
                "type": "surface_state",
                "ref": "surface:42",
                "name": "random-tab-title",
                "expected_canonical": "ATDD513-coach-v9-l4-babysit-absorbed-rules",
            },
        ),
    )
    assert canonical_naming_drift.predicate(ctx) is True


def test_rule_14_predicate_silent_when_surface_already_canonical():
    """Surfaces already at canonical names do not fire — drift-detection only."""
    from atdd.coach.observer_rules import canonical_naming_drift

    canonical = "ATDD513-coach-v9-l4-babysit-absorbed-rules"
    assert session_naming.is_canonical_name(canonical), (
        "test fixture must use a canonical name"
    )
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        events=(
            {
                "type": "surface_state",
                "ref": "surface:42",
                "name": canonical,
                "expected_canonical": canonical,
            },
        ),
    )
    assert canonical_naming_drift.predicate(ctx) is False


def test_rule_14_predicate_silent_when_no_surface_state_events():
    from atdd.coach.observer_rules import canonical_naming_drift

    ctx = observer.ObservedInput(agent_id="agent-A")
    assert canonical_naming_drift.predicate(ctx) is False


# ---------------------------------------------------------------------------
# Parity with babysit.correct_naming_drift — re-applies within one tick + logs
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_rule_14_apply_correction_re_applies_canonical_name_within_one_tick(
    tmp_path: Path,
):
    """``apply_correction(backend, ctx, log_path, applied_cache)`` must call
    babysit.correct_naming_drift, which renames the surface AND logs the
    structured ``coach.orchestration.canonical-session-name`` event."""
    from atdd.coach.observer_rules import canonical_naming_drift

    backend = _StubBackend()
    log_path = tmp_path / "orchestration-log.jsonl"
    applied_cache: Dict[str, str] = {}

    canonical = "ATDD513-coach-v9-l4-babysit-absorbed-rules"
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        events=(
            {
                "type": "surface_state",
                "ref": "surface:42",
                "name": "drifted-name",
                "expected_canonical": canonical,
            },
        ),
    )
    canonical_naming_drift.apply_correction(
        ctx, backend=backend, log_path=log_path, applied_cache=applied_cache,
    )

    assert backend.renames == [("surface:42", canonical)], (
        "rule 14 must call backend.rename with the canonical name within one tick"
    )

    events = _read_jsonl(log_path)
    rule_id_events = [
        e for e in events if e.get("rule_id") == "coach.orchestration.canonical-session-name"
    ]
    assert rule_id_events, (
        "rule 14 must log coach.orchestration.canonical-session-name"
    )


def test_rule_14_apply_correction_idempotent_on_canonical_surface(
    tmp_path: Path,
):
    """Already-canonical surfaces produce no rename and no log event."""
    from atdd.coach.observer_rules import canonical_naming_drift

    backend = _StubBackend()
    log_path = tmp_path / "orchestration-log.jsonl"
    applied_cache: Dict[str, str] = {}

    canonical = "ATDD513-coach-v9-l4-babysit-absorbed-rules"
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        events=(
            {
                "type": "surface_state",
                "ref": "surface:42",
                "name": canonical,
                "expected_canonical": canonical,
            },
        ),
    )
    canonical_naming_drift.apply_correction(
        ctx, backend=backend, log_path=log_path, applied_cache=applied_cache,
    )

    assert backend.renames == []
    assert _read_jsonl(log_path) == []
