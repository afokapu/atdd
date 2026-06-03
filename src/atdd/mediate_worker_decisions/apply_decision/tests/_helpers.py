"""Shared test doubles for apply-decision."""
from __future__ import annotations

from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    AUTO_APPLY, HUMAN_REQUIRED, SOURCE_COACH, SOURCE_SAFETY_GATE, Verdict,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionPrompt, DecisionRequest, Option, WorkerRef,
)


def make_request(request_id="req-1", surface="surface:3"):
    return DecisionRequest(
        request_id=request_id,
        worker=WorkerRef(surface_id=surface, run_id="run-1", agent_handle_ref="h-3"),
        prompt=DecisionPrompt(
            raw_text="Proceed?", question="Proceed?",
            options=(Option("1", "Yes"), Option("2", "No")),
        ),
        source="cmux_notification", created_at="t",
    )


def make_verdict(verdict_id="ver-1", request_id="req-1", auto=True):
    if auto:
        return Verdict(verdict_id, request_id, "t", AUTO_APPLY, SOURCE_COACH,
                       selected_option_id="1", reason="ok")
    return Verdict(verdict_id, request_id, "t", HUMAN_REQUIRED, SOURCE_SAFETY_GATE,
                   selected_option_id=None, reason="dangerous")


class FakeApplier:
    def __init__(self, raises=False):
        self.calls = []
        self._raises = raises

    def apply(self, handle_ref, instruction):
        self.calls.append((handle_ref, instruction))
        if self._raises:
            raise RuntimeError("deliver failed")


class FakeLedger:
    def __init__(self):
        self.records = []

    def record(self, record):
        self.records.append(record)


def fixed_id():
    return "id-fixed"


def fixed_ts():
    return "2026-06-03T00:00:00+00:00"
