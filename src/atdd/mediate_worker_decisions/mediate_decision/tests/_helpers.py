"""Shared test doubles for mediate-decision."""
from __future__ import annotations

from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionPrompt,
    DecisionRequest,
    Option,
    WorkerRef,
)


def make_request(question="Proceed?", options=(("1", "Yes"), ("2", "No")),
                 request_id="req-1", surface="surface:3"):
    return DecisionRequest(
        request_id=request_id,
        worker=WorkerRef(surface_id=surface, run_id="run-1"),
        prompt=DecisionPrompt(
            raw_text=question, question=question,
            options=tuple(Option(i, l) for i, l in options),
        ),
        source="cmux_notification",
        created_at="t",
    )


class FakeCoach:
    def __init__(self, reply=""):
        self.reply = reply
        self.presented = []

    def present(self, text):
        self.presented.append(text)

    def read_reply(self):
        return self.reply


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class FakeSink:
    def __init__(self):
        self.records = []

    def emit(self, record):
        self.records.append(record)


def fixed_id():
    return "id-fixed"


def fixed_ts():
    return "2026-06-03T00:00:00+00:00"
