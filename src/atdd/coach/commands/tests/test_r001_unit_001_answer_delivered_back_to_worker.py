# URN: test:observe-and-correct:worker-coach-event-loop:R001-UNIT-001-answer-delivered-back-to-worker
# Acceptance: acc:observe-and-correct:R001-UNIT-001-answer-delivered-back-to-worker
# WMBT: wmbt:observe-and-correct:R001
# Phase: RED
# Layer: application
"""R001-UNIT-001 — an answer to an ``ask`` event is delivered back into
the worker via the observer return-path, not merely recorded.

Issue #731 Phase 3 — an ``ask`` that is only logged leaves the worker
blocked forever; the answer must round-trip so the worker can read it
back (``agent.read_answer`` → ``answers/<qid>.json``).

RED: the observer has no answer-delivery surface, so ``read_answer``
returns ``None`` for the asked question.
"""
from __future__ import annotations

from pathlib import Path

OBSERVER_ID = "coder-731-ans1-observer"
WORKER_ID = "coder-731-ans1"


def _observer(runtime: Path):
    from atdd.coach.commands.observer import Observer

    return Observer(agent_id=OBSERVER_ID, runtime_dir=runtime, rules_dir=None)


def _ask(runtime: Path) -> str:
    """The worker (here, the observer on its behalf) asks a question."""
    from atdd.coach.commands import agent

    record = agent.cmd_ask(
        question="env injection in adapter or cmd_spawn?",
        type="text",
        agent_id=WORKER_ID,
        runtime_root=runtime,
    )
    return record["question_id"]


def test_delivered_answer_is_readable_by_the_worker(tmp_path):
    from atdd.coach.commands import agent

    runtime = tmp_path / "rt"
    question_id = _ask(runtime)
    obs = _observer(runtime)

    # The coach/operator answer is routed back into the worker.
    obs.deliver_answer(question_id, "Inject it in cmd_spawn.")

    answer = agent.read_answer(
        question_id=question_id, agent_id=WORKER_ID, runtime_root=runtime,
    )
    assert answer is not None, "answer never round-tripped — worker stays blocked"
    assert "cmd_spawn" in json_text(answer)


def test_delivered_answer_correlates_to_the_originating_question(tmp_path):
    from atdd.coach.commands import agent

    runtime = tmp_path / "rt"
    question_id = _ask(runtime)
    obs = _observer(runtime)
    obs.deliver_answer(question_id, "Inject it in cmd_spawn.")

    # An unrelated question id must NOT resolve to this answer.
    other = agent.read_answer(
        question_id="q-does-not-exist", agent_id=WORKER_ID, runtime_root=runtime,
    )
    assert other is None
    delivered = agent.read_answer(
        question_id=question_id, agent_id=WORKER_ID, runtime_root=runtime,
    )
    assert delivered is not None


def json_text(value: object) -> str:
    import json

    return json.dumps(value)
