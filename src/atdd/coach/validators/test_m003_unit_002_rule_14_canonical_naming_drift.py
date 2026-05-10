# URN: component:observe-and-correct:observer-runtime-and-rules:test_m003_unit_002_rule_14_canonical_naming_drift:backend:domain
# Runtime: python
# Purpose: Reverse-coherence binding for coach.observer.canonical-naming-drift (rule 14).

"""Validator wrapper for observer rule 14 (issue #513).

Binds ``coach.observer.canonical-naming-drift`` and asserts the absorption-
pattern parity between the rule and ``babysit.correct_naming_drift`` per
spec §0.2. Detailed parity tests live at
``src/atdd/coach/commands/tests/test_m003_unit_002_rule_14_canonical_naming_drift.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import pytest

from atdd.coach.commands import babysit, observer
from atdd.coach.observer_rules import canonical_naming_drift
from atdd.coach.utils import session_naming
from atdd.coach.utils.rule_binding import bind_rule


_RULE = bind_rule("coach.observer.canonical-naming-drift")


pytestmark = [pytest.mark.coach]


class _StubBackend:
    name = "stub"

    def __init__(self) -> None:
        self.renames: List[Tuple[str, str]] = []
        self.sends: List[Tuple[str, str]] = []

    def rename(self, ref: str, new_name: str) -> None:
        self.renames.append((ref, new_name))

    def send(self, ref: str, text: str) -> None:
        self.sends.append((ref, text))


def test_rule_14_parity_with_correct_naming_drift(tmp_path: Path):
    """Rule 14 detects drift via is_canonical_name and re-applies via
    correct_naming_drift, logging coach.orchestration.canonical-session-name."""
    assert _RULE.rule_id == "coach.observer.canonical-naming-drift"

    # Absorption: verbatim helpers per spec §0.2.
    assert canonical_naming_drift.correct_naming_drift is babysit.correct_naming_drift
    assert canonical_naming_drift.is_canonical_name is session_naming.is_canonical_name

    canonical = "ATDD513-coach-v9-l4-babysit-absorbed-rules"
    drifted_ctx = observer.ObservedInput(
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
    canonical_ctx = observer.ObservedInput(
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
    assert canonical_naming_drift.predicate(drifted_ctx) is True
    assert canonical_naming_drift.predicate(canonical_ctx) is False

    backend = _StubBackend()
    log_path = tmp_path / "orchestration-log.jsonl"
    canonical_naming_drift.apply_correction(
        drifted_ctx,
        backend=backend,
        log_path=log_path,
        applied_cache={},
    )
    assert backend.renames == [("surface:42", canonical)]
    events = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        e.get("rule_id") == "coach.orchestration.canonical-session-name"
        for e in events
    )
