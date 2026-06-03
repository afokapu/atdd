# URN: test:mediate-worker-decisions:sense-decision:D001-INTEGRATION-001-entry-path-parity
# Acceptance: acc:mediate-worker-decisions:D001-INTEGRATION-001-entry-path-parity
# WMBT: wmbt:mediate-worker-decisions:D001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""D001-INTEGRATION-001 — notify-hook and emit-CLI serialize identical requests."""
from __future__ import annotations

from atdd.mediate_worker_decisions.sense_decision.composition import build_sense_use_case
from atdd.mediate_worker_decisions.sense_decision.src.application.sense_use_case import (
    SOURCE_NOTIFICATION,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    Option,
    WorkerRef,
)
from atdd.mediate_worker_decisions.sense_decision.src.presentation.emit_cli import emit_request


class _Reader:
    def __init__(self, text):
        self._text = text

    def read(self, surface_id):
        return self._text


class _Registry:
    def resolve(self, surface_id):
        return WorkerRef(surface_id=surface_id, run_id="run-1")


class _Sink:
    def __init__(self):
        self.records = []

    def emit(self, request):
        self.records.append(request)


def _fixed_ids():
    return "req-fixed"


def _fixed_clock():
    return "2026-06-03T00:00:00+00:00"


def test_d001_integration_001_entry_path_parity():
    prompt_text = "Proceed?\n1) Yes\n2) No\n"
    sink = _Sink()

    # notify path: sense reads + parses the surface
    uc = build_sense_use_case(
        reader=_Reader(prompt_text),
        registry=_Registry(),
        sink=sink,
        id_factory=_fixed_ids,
        clock=_fixed_clock,
    )
    uc.sense(surface_id="surface:3", source=SOURCE_NOTIFICATION)

    # emit path: same worker + prompt, fed directly through the SAME sink
    emit_request(
        sink=sink,
        surface_id="surface:3",
        question="Proceed?",
        options=[Option("1", "Yes"), Option("2", "No")],
        id_factory=_fixed_ids,
        clock=_fixed_clock,
        run_id="run-1",
    )

    notify_c = sink.records[0].to_contract()
    emit_c = sink.records[1].to_contract()
    # identical except provenance.source
    assert notify_c["provenance"]["source"] == "cmux_notification"
    assert emit_c["provenance"]["source"] == "emit_cli"
    notify_c["provenance"].pop("source")
    notify_c["provenance"].pop("notification_hash", None)
    emit_c["provenance"].pop("source")
    # raw_text is captured evidence (surface tail vs given question) and is
    # allowed to differ; the routed question/options/worker must be identical.
    notify_c["prompt"].pop("raw_text")
    emit_c["prompt"].pop("raw_text")
    assert notify_c == emit_c
