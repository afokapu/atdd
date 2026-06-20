# URN: test:atdd-plan-core:elicit-contract:shape-and-invariants
# Issue: #1139 (consumes #1096a)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1096a elicit contract (#1139 dependency) — shape + invariants.

Asserts the ratified contract: actor-neutral participation roles, the
InlineClaudeElicitAdapter round-trip, the flat-but-stable selections rule,
elicit_id echo enforcement, and the #1139 plan-session role binding
(origin=conductor/planner, resolved_by=operator).
"""
from __future__ import annotations

import pytest

from atdd.runtime.elicit import (
    AtddRole, DefaultPolicy, Elicit, ElicitContractError, ElicitKind,
    ElicitRequest, ElicitResponse, ElicitRisk, ElicitStatus, ElicitRole,
    InlineClaudeElicitAdapter, Participant, validate_selections,
)


def _keep_pivot_kill_request():
    return ElicitRequest(
        elicit_id="plan-sess-1:wagon:demo:turn-1",
        origin=Participant(ElicitRole.CONDUCTOR, "atdd-plan-session:s1", AtddRole.PLANNER),
        kind=ElicitKind.CONFIRMATION,
        prompt="Keep, pivot, or kill the wagon 'demo'?",
        risk=ElicitRisk.NEEDS_HUMAN,
        questions=[{"id": "verdict", "prompt": "demo?", "multiSelect": False,
                    "options": [{"label": "keep"}, {"label": "pivot"}, {"label": "kill"}]}],
        default_policy=DefaultPolicy.ESCALATE,
    )


def test_participation_roles_are_actor_neutral_not_disciplines():
    assert {r.value for r in ElicitRole} == {"worker", "conductor", "operator"}
    # discipline rides as optional metadata, never the participation enum
    assert "coach" not in {r.value for r in ElicitRole}
    assert AtddRole.COACH.value == "coach"


def test_inline_adapter_round_trips_and_is_an_elicit():
    req = _keep_pivot_kill_request()

    def resolver(r: ElicitRequest) -> ElicitResponse:
        return ElicitResponse(
            elicit_id=r.elicit_id, status=ElicitStatus.RESOLVED,
            resolved_by=Participant(ElicitRole.OPERATOR, "user"),
            selections=["keep"],
        )

    adapter: Elicit = InlineClaudeElicitAdapter(resolver)
    resp = adapter.elicit(req)
    assert resp.status is ElicitStatus.RESOLVED
    assert resp.selections == ["keep"]
    assert resp.resolved_by.elicit_role is ElicitRole.OPERATOR
    assert resp.resolved_by.atdd_role is None  # the human operator carries no discipline


def test_selections_must_be_flat_unique_and_offered():
    req = _keep_pivot_kill_request()
    validate_selections(req, ["keep"])              # ok
    with pytest.raises(ElicitContractError):
        validate_selections(req, ["keep", "keep"])  # not unique
    with pytest.raises(ElicitContractError):
        validate_selections(req, [["keep"]])        # nested
    with pytest.raises(ElicitContractError):
        validate_selections(req, ["yes"])           # not offered by the request


def test_adapter_enforces_elicit_id_echo():
    req = _keep_pivot_kill_request()

    def bad_resolver(r):
        return ElicitResponse(elicit_id="WRONG", status=ElicitStatus.RESOLVED,
                              resolved_by=Participant(ElicitRole.OPERATOR, "user"), selections=["keep"])

    with pytest.raises(ElicitContractError):
        InlineClaudeElicitAdapter(bad_resolver).elicit(req)


def test_plan_session_role_binding_matches_1139():
    req = _keep_pivot_kill_request()
    assert req.origin.elicit_role is ElicitRole.CONDUCTOR
    assert req.origin.atdd_role is AtddRole.PLANNER
    assert req.kind is ElicitKind.CONFIRMATION  # keep/pivot/kill rides confirmation
