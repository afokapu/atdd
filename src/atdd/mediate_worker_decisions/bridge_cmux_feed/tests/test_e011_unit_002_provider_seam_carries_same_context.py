# URN: test:mediate-worker-decisions:bridge-cmux-feed:E011-UNIT-002-provider-seam-carries-same-context
# Acceptance: acc:mediate-worker-decisions:E011-UNIT-002-provider-seam-carries-same-context
# WMBT: wmbt:mediate-worker-decisions:E011
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E011-UNIT-002 — the provider seam carries the SAME coach context to any provider.

Loading the coach convention is not claude-specific. An alternate provider
registered in the pluggable seam must receive the exact same coach context the
decider would hand claude — proving the context flows to whatever provider the
decider resolves, not just ``claude -p``.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration import llm_coach
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.llm_coach import (
    LlmCoach,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionPrompt,
    DecisionRequest,
    Option,
    WorkerRef,
)

_COACH_CONTEXT = "CTX-MARKER-coach-convention-and-operating-protocol"


def _single_request() -> DecisionRequest:
    return DecisionRequest(
        request_id="req-2",
        worker=WorkerRef(surface_id="s1", agent_handle_ref="req-2"),
        prompt=DecisionPrompt(
            raw_text="",
            question="pick one",
            options=(Option("a", "Alpha"), Option("b", "Beta")),
        ),
        source="cmux_feed",
        created_at="",
    )


def test_alternate_provider_receives_the_same_coach_context(monkeypatch):
    seen = {}

    def _alt_factory(model):
        def run(prompt, *, system=None, timeout):
            seen["system"] = system
            return "Alpha"
        return run

    # register an alternate provider in the pluggable seam (the only seam point)
    monkeypatch.setitem(llm_coach._PROVIDER_CLI_FACTORIES, "altprov", _alt_factory)

    coach = LlmCoach(
        provider="altprov",
        coach_context=_COACH_CONTEXT,
        id_factory=lambda: "v",
        ts_factory=lambda: "t",
    )
    coach.mediate(_single_request())

    assert seen["system"] == _COACH_CONTEXT
