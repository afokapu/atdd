# URN: test:atdd-plan-core:session-machine:gates-and-confirm-before-author
# Issue: #1139
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1139 — the atdd plan gated session state machine.

Covers durable save/load, the stage gate exit-conditions, keep/pivot/kill via
the elicit channel, the Confirm lock, and confirm-before-author (no authoring
before the operator confirms).
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit, Verdict,
)
from atdd.runtime.elicit import (
    ElicitResponse, ElicitStatus, ElicitRole, Participant, InlineClaudeElicitAdapter,
)


def _op_resolver(choice):
    def r(req):
        return ElicitResponse(elicit_id=req.elicit_id, status=ElicitStatus.RESOLVED,
                              resolved_by=Participant(ElicitRole.OPERATOR, "user"),
                              selections=[choice])
    return InlineClaudeElicitAdapter(r)


def test_save_load_round_trip(tmp_path):
    s = PlanSession("s1", main_job="Listen to music while commuting")
    s.add_unit(Unit(kind="wagon", ref="play-audio"))
    s.save(tmp_path)
    loaded = PlanSession.load("s1", tmp_path)
    assert loaded.main_job == s.main_job
    assert loaded.units[0]["ref"] == "play-audio"


def test_gates_block_until_exit_condition_met():
    s = PlanSession("s1")
    with pytest.raises(SessionGateError):       # Define needs a kept main job
        s.advance(Step.ATTACH)
    s.main_job = "Listen to music while commuting"
    s.advance(Step.ATTACH)
    with pytest.raises(SessionGateError):       # Locate needs sources
        s.advance(Step.COMPOSE)
    s.sources.append({"type": "text", "value": "spec"})
    s.advance(Step.COMPOSE)
    with pytest.raises(SessionGateError):       # Prepare needs a candidate unit
        s.advance(Step.RATIFY)
    s.add_unit(Unit(kind="wagon", ref="play-audio"))
    s.advance(Step.RATIFY)
    assert s.step == Step.RATIFY.value


def test_cannot_skip_steps():
    s = PlanSession("s1", main_job="x")
    with pytest.raises(SessionGateError):
        s.advance(Step.COMPOSE)  # from DEFINE, skipping LOCATE


def test_backtracking_allowed():
    s = PlanSession("s1", main_job="x")
    s.advance(Step.ATTACH)
    s.advance(Step.INTENT)       # backtrack — no gate
    assert s.step == Step.INTENT.value


def test_decide_records_verdict_via_elicit():
    s = PlanSession("s1")
    s.add_unit(Unit(kind="wagon", ref="play-audio"))
    s.decide("play-audio", _op_resolver("keep"))
    assert s._unit("play-audio")["verdict"] == Verdict.KEEP.value
    assert s.kept_units()[0]["ref"] == "play-audio"


def test_confirm_requires_all_resolved_then_locks():
    s = PlanSession("s1", main_job="x", step=Step.RATIFY.value, issue_ref="my-plan")
    s.add_unit(Unit(kind="wagon", ref="play-audio"))  # PENDING
    with pytest.raises(SessionGateError):
        s.confirm()
    s.decide("play-audio", _op_resolver("keep"))
    s.confirm()
    assert s.locked is True


def test_confirm_before_author_refuses_authoring_until_locked():
    s = PlanSession("s1", step=Step.RATIFY.value, issue_ref="my-plan")
    s.add_unit(Unit(kind="wagon", ref="play-audio", spec={"wagon": "play-audio"}))
    authored = []
    with pytest.raises(SessionGateError):              # not locked yet
        s.author(lambda kind, spec: authored.append((kind, spec)))
    s.decide("play-audio", _op_resolver("keep"))
    s.confirm()
    s.author(lambda kind, spec: authored.append((kind, spec)))
    assert authored == [("wagon", {"wagon": "play-audio"})]
    assert s.step == Step.AUTHORED.value


def test_killed_units_are_not_authored():
    s = PlanSession("s1", step=Step.RATIFY.value, issue_ref="my-plan")
    s.add_unit(Unit(kind="wagon", ref="keep-me", spec={"wagon": "keep-me"}))
    s.add_unit(Unit(kind="wagon", ref="kill-me", spec={"wagon": "kill-me"}))
    s.decide("keep-me", _op_resolver("keep"))
    s.decide("kill-me", _op_resolver("kill"))
    s.confirm()
    authored = []
    s.author(lambda kind, spec: authored.append(spec["wagon"]))
    assert authored == ["keep-me"]


def test_confirm_refuses_unresolved_pivot_until_re_resolved():
    """A pivot is non-terminal: confirm refuses until it is re-resolved to keep/kill."""
    s = PlanSession("s1", step=Step.RATIFY.value, issue_ref="my-plan")
    s.add_unit(Unit(kind="wagon", ref="w"))
    s.decide("w", _op_resolver("pivot"))
    with pytest.raises(SessionGateError):
        s.confirm()
    s.decide("w", _op_resolver("keep"))   # operator re-drafts + re-decides
    s.confirm()
    assert s.locked is True
