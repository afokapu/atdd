# URN: test:observe-and-correct:worker-coach-event-loop:R001-UNIT-002-roundtrip-delivery-is-adapter-agnostic
# Acceptance: acc:observe-and-correct:R001-UNIT-002-roundtrip-delivery-is-adapter-agnostic
# WMBT: wmbt:observe-and-correct:R001
# Phase: RED
# Layer: application
"""R001-UNIT-002 — the answer-delivery path is adapter-neutral: it uses
the observer's existing injection machinery and no Claude-Code-specific
hook, so every ``ADAPTER_REGISTRY`` adapter inherits the round-trip.

RED: the observer has no ``deliver_answer`` surface at all.
"""
from __future__ import annotations

import inspect
from pathlib import Path

OBSERVER_ID = "tester-731-ans2-observer"
WORKER_ID = "tester-731-ans2"


def _ask(runtime: Path) -> str:
    from atdd.coach.commands import agent

    return agent.cmd_ask(
        question="which approach?", type="choice",
        agent_id=WORKER_ID, runtime_root=runtime,
    )["question_id"]


def test_observer_exposes_an_answer_delivery_surface(tmp_path):
    from atdd.coach.commands.observer import Observer

    assert hasattr(Observer, "deliver_answer"), (
        "Observer has no deliver_answer — the ask round-trip is unimplemented"
    )


def test_delivery_signature_carries_no_adapter_parameter(tmp_path):
    """Adapter-agnosticism: delivery is keyed on question id + answer only;
    it never takes an adapter / llm / hook argument."""
    from atdd.coach.commands.observer import Observer

    sig = inspect.signature(Observer.deliver_answer)
    assert not (set(sig.parameters) & {"adapter", "llm", "adapter_name", "hook"})


def test_delivery_works_through_the_generic_runtime_for_every_adapter(tmp_path):
    """The observer is never told the worker's LLM; delivery must still
    land the answer in the generic runtime tree for any adapter."""
    from atdd.coach.commands import agent
    from atdd.coach.commands.observer import Observer

    runtime = tmp_path / "rt"
    question_id = _ask(runtime)
    obs = Observer(agent_id=OBSERVER_ID, runtime_dir=runtime, rules_dir=None)
    obs.deliver_answer(question_id, "Option A")

    answer = agent.read_answer(
        question_id=question_id, agent_id=WORKER_ID, runtime_root=runtime,
    )
    assert answer is not None, "answer not delivered through the generic runtime path"
