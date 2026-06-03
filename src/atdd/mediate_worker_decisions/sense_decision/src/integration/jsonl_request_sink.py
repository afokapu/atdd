"""RequestSink adapter: append the request contract as one JSONL line.

Single-writer append (via the wagon commons writer); the bridge uses its own
``.atdd/decision/`` namespace to avoid contending with the coach run's
``decisions.jsonl`` (single-writer invariant).
"""
from __future__ import annotations

from pathlib import Path

from atdd.mediate_worker_decisions.commons.jsonl_writer import append_jsonl
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionRequest,
)


class JsonlRequestSink:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def emit(self, request: DecisionRequest) -> None:
        append_jsonl(self._path, request.to_contract())
