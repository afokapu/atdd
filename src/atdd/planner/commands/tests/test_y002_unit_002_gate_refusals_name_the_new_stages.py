# URN: test:define-plans:atdd-plan-session:Y002-UNIT-002-gate-refusals-name-the-new-stages
# Acceptance: acc:define-plans:Y002-UNIT-002-gate-refusals-name-the-new-stages
# WMBT: wmbt:define-plans:Y002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""Y002-UNIT-002 — every gate refusal names the stage whose exit condition failed.

Note the direction: a refusal message names the stage being *left*, not the one
being entered. `_gate_ok(ATTACH)` explains why Intent will not release the
session, so the four messages track Intent/Attach/Compose/Ratify while the four
branch targets are Attach/Compose/Ratify/Authored. Renaming each message to
match its own branch target would silently invert all four.

RED: the refusals still say Define / Locate / Prepare / Confirm.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.plan_session import PlanSession, SessionGateError, Step

RETIRED_STAGE_WORDS = ["Define", "Locate", "Prepare", "Confirm"]


def _refusal(session: PlanSession, target: Step) -> str:
    with pytest.raises(SessionGateError) as exc:
        session.advance(target)
    return str(exc.value)


def test_refusal_leaving_intent_names_intent():
    msg = _refusal(PlanSession("y002-r1"), Step.ATTACH)
    assert "Intent" in msg


def test_refusal_leaving_attach_names_attach():
    s = PlanSession("y002-r2", step=Step.ATTACH.value, main_job="a job")
    assert "Attach" in _refusal(s, Step.COMPOSE)


def test_refusal_leaving_compose_names_compose():
    s = PlanSession("y002-r3", step=Step.COMPOSE.value, main_job="a job",
                    sources=[{"type": "text", "value": "spec"}])
    assert "Compose" in _refusal(s, Step.RATIFY)


def test_refusal_blocking_authoring_names_ratify():
    s = PlanSession("y002-r4", step=Step.RATIFY.value, main_job="a job",
                    sources=[{"type": "text", "value": "spec"}])
    s.units.append({"kind": "wmbt", "ref": "wmbt:define-plans:Z001",
                    "verdict": "keep", "modification": None, "spec": {}})
    assert "Ratify" in _refusal(s, Step.AUTHORED)


def test_no_gate_refusal_carries_a_retired_stage_name():
    """The sweep: none of the four messages may still name an old stage.

    `confirm-before-author` survives as a RULE name and is asserted elsewhere —
    what may not survive is a retired word used as a STAGE name in operator
    output.
    """
    fresh = PlanSession("y002-s1")
    attaching = PlanSession("y002-s2", step=Step.ATTACH.value, main_job="a job")
    composing = PlanSession("y002-s3", step=Step.COMPOSE.value, main_job="a job",
                            sources=[{"type": "text", "value": "spec"}])
    ratifying = PlanSession("y002-s4", step=Step.RATIFY.value, main_job="a job",
                            sources=[{"type": "text", "value": "spec"}])
    ratifying.units.append({"kind": "wmbt", "ref": "wmbt:define-plans:Z001",
                            "verdict": "keep", "modification": None, "spec": {}})

    messages = [
        _refusal(fresh, Step.ATTACH),
        _refusal(attaching, Step.COMPOSE),
        _refusal(composing, Step.RATIFY),
        _refusal(ratifying, Step.AUTHORED),
    ]
    for msg in messages:
        for retired in RETIRED_STAGE_WORDS:
            assert retired not in msg, f"gate refusal still names {retired!r}: {msg}"


def test_skip_refusal_reports_the_new_stage_values():
    s = PlanSession("y002-skip", main_job="a job")
    with pytest.raises(SessionGateError) as exc:
        s.advance(Step.COMPOSE)
    msg = str(exc.value)
    assert "intent" in msg and "compose" in msg
