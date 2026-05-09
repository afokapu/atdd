# URN: test:drive-state-machine:coach-state-machine-and-runtime:D002-UNIT-003-ask-answer-roundtrip
# Acceptance: acc:drive-state-machine:D002-UNIT-003-ask-answer-roundtrip
# WMBT: wmbt:drive-state-machine:D002
# Phase: RED
# Layer: application
"""D002-UNIT-003 — `atdd agent ask` writes a question record to
`questions.jsonl`; coach answers via `answers/<question-id>.json`.

J2 ships only the agent (write) side. The coach side is a fixture-only
mock here — we just simulate the file write coach is contracted to do
and assert the round-trip path is keyed by `question_id` with no shared
mutable state between the two sides.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


@pytest.fixture
def runtime_root(tmp_path: Path) -> Path:
    return tmp_path / ".atdd" / "runtime"


@pytest.fixture
def agent_id() -> str:
    return "agent-J2-test"


@pytest.mark.parametrize(
    "qtype", ["choice", "text", "approval", "confirmation"],
)
def test_ask_record_carries_question_id_type_text_timestamp(
    runtime_root: Path, agent_id: str, qtype: str,
):
    from atdd.coach.commands import agent

    record = agent.cmd_ask(
        question="should we proceed?",
        type=qtype,
        agent_id=agent_id,
        runtime_root=runtime_root,
    )
    assert set(record.keys()) >= {"question_id", "type", "question", "timestamp"}
    assert record["type"] == qtype
    assert record["question"] == "should we proceed?"
    assert record["timestamp"].endswith("Z")
    # question_id must be url-safe-ish (no whitespace, non-empty)
    assert record["question_id"]
    assert " " not in record["question_id"]


def test_ask_question_id_is_unique_across_calls(
    runtime_root: Path, agent_id: str,
):
    from atdd.coach.commands import agent

    ids = {
        agent.cmd_ask(
            question=f"q{i}",
            type="text",
            agent_id=agent_id,
            runtime_root=runtime_root,
        )["question_id"]
        for i in range(5)
    }
    assert len(ids) == 5


def test_round_trip_path_is_keyed_by_question_id(
    runtime_root: Path, agent_id: str,
):
    """Coach writes its answer to
    `.atdd/runtime/agents/<id>/answers/<question-id>.json` keyed by the
    same `question_id` the agent recorded. The round-trip path is the
    whole contract — no shared mutable state."""
    from atdd.coach.commands import agent

    record = agent.cmd_ask(
        question="proceed with refactor?",
        type="approval",
        agent_id=agent_id,
        runtime_root=runtime_root,
    )
    qid = record["question_id"]

    # Simulate coach writing the answer file (out of J2 scope; this is the
    # contract J5/J3 will satisfy on the read side).
    answers_dir = runtime_root / "agents" / agent_id / "answers"
    answers_dir.mkdir(parents=True, exist_ok=True)
    answer_payload = {"question_id": qid, "answer": "yes", "answered_at": "2026-05-09T12:00:00Z"}
    (answers_dir / f"{qid}.json").write_text(json.dumps(answer_payload))

    # The agent helper used to look up an answer must find this file by qid.
    answer = agent.read_answer(
        question_id=qid, agent_id=agent_id, runtime_root=runtime_root,
    )
    assert answer == answer_payload


def test_read_answer_returns_none_when_unanswered(
    runtime_root: Path, agent_id: str,
):
    from atdd.coach.commands import agent

    record = agent.cmd_ask(
        question="q?",
        type="text",
        agent_id=agent_id,
        runtime_root=runtime_root,
    )
    assert (
        agent.read_answer(
            question_id=record["question_id"],
            agent_id=agent_id,
            runtime_root=runtime_root,
        )
        is None
    )


def test_questions_jsonl_is_append_only_across_asks(
    runtime_root: Path, agent_id: str,
):
    from atdd.coach.commands import agent

    r1 = agent.cmd_ask(
        question="q1", type="text",
        agent_id=agent_id, runtime_root=runtime_root,
    )
    r2 = agent.cmd_ask(
        question="q2", type="text",
        agent_id=agent_id, runtime_root=runtime_root,
    )
    path = runtime_root / "agents" / agent_id / "questions.jsonl"
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["question_id"] == r1["question_id"]
    assert json.loads(lines[1])["question_id"] == r2["question_id"]
