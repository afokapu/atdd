# URN: test:define-plans:atdd-plan-session:Y002-UNIT-003-reopen-returns-to-compose
# Acceptance: acc:define-plans:Y002-UNIT-003-reopen-returns-to-compose
# WMBT: wmbt:define-plans:Y002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""Y002-UNIT-003 — reopen lands a locked session on Compose and says so.

`reopen()` is the sanctioned withdrawal of the operator's lock, and the refusal
raised by a locked mutation is where an operator is *told* how to withdraw it.
That message names two stages — the lock (Ratify) and where reopen returns to
(Compose) — so it moves with the rename or it sends operators to a stage that
no longer exists.

RED: reopen still targets PREPARE and the refusal still says Confirm / Prepare.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit,
)


def _locked_at_ratify(session_id: str = "y002-locked") -> PlanSession:
    s = PlanSession(session_id, step=Step.RATIFY.value, main_job="a job",
                    sources=[{"type": "text", "value": "spec"}], locked=True)
    s.units.append({"kind": "wmbt", "ref": "wmbt:define-plans:Z001",
                    "verdict": "keep", "modification": None, "spec": {}})
    return s


def test_reopen_returns_a_locked_session_to_compose():
    s = _locked_at_ratify()
    s.reopen()
    assert s.step == Step.COMPOSE.value
    assert s.locked is False


def test_reopen_preserves_verdicts():
    """Unchanged behaviour, re-pinned: the rename must not quietly reset verdicts."""
    s = _locked_at_ratify()
    s.reopen()
    assert [u["verdict"] for u in s.units] == ["keep"]


def test_locked_mutation_refusal_names_ratify_and_compose():
    s = _locked_at_ratify()
    with pytest.raises(SessionGateError) as exc:
        s.add_unit(Unit(kind="wmbt", ref="wmbt:define-plans:Z002"))
    msg = str(exc.value)
    assert "Ratify" in msg, f"lock refusal does not name Ratify: {msg}"
    assert "Compose" in msg, f"lock refusal does not name Compose: {msg}"
    assert "Confirm" not in msg and "Prepare" not in msg


def test_reopen_is_still_refused_once_authored():
    s = PlanSession("y002-authored", step=Step.AUTHORED.value, locked=True)
    with pytest.raises(SessionGateError) as exc:
        s.reopen()
    assert "authored" in str(exc.value).lower()
