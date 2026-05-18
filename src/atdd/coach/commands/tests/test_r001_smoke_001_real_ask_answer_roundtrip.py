# URN: test:observe-and-correct:worker-coach-event-loop:R001-SMOKE-001-real-ask-answer-roundtrip
# Acceptance: acc:observe-and-correct:R001-SMOKE-001-real-ask-answer-roundtrip
# WMBT: wmbt:observe-and-correct:R001
# Phase: SMOKE
# Layer: integration
# Harness: smoke/backend
"""R001-SMOKE-001 — an end-to-end real round-trip: a worker's ``ask`` is
answered and the answer reaches the worker through real runtime files.

SMOKE: no mocks. A real ``atdd agent ask`` records the question, the real
observer delivers the answer, and a real ``agent.read_answer`` reads it
back — the full worker->coach->worker loop on the real filesystem.

RED: the observer has no answer-delivery surface, so the round-trip
cannot complete and ``read_answer`` returns ``None``.
"""
from __future__ import annotations

from pathlib import Path

OBSERVER_ID = "coder-731-anss-observer"
WORKER_ID = "coder-731-anss"


def test_real_ask_answer_roundtrip_reaches_the_worker(tmp_path):
    from atdd.coach.commands import agent
    from atdd.coach.commands.observer import Observer

    runtime = tmp_path / "rt"

    # Real ask: the worker records a real question in questions.jsonl.
    asked = agent.cmd_ask(
        question="Should ATDD_AGENT_ID injection live in the adapter?",
        type="confirmation",
        agent_id=WORKER_ID,
        runtime_root=runtime,
    )
    question_id = asked["question_id"]
    assert (runtime / "agents" / WORKER_ID / "questions.jsonl").exists()

    # Real delivery: the observer round-trips the operator's answer.
    obs = Observer(agent_id=OBSERVER_ID, runtime_dir=runtime, rules_dir=None)
    obs.deliver_answer(question_id, "No — inject it in cmd_spawn.")

    # Real read-back: the worker reads its answer from the real runtime tree.
    answer = agent.read_answer(
        question_id=question_id, agent_id=WORKER_ID, runtime_root=runtime,
    )
    assert answer is not None, (
        "ask was recorded but the answer never reached the worker — "
        "the round-trip is incomplete and the worker stays blocked"
    )
