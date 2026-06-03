"""RequestSink adapter: append the request contract as one JSONL line.

Single-writer append; the bridge uses its own ``.atdd/decision/`` namespace to
avoid contending with the coach run's ``decisions.jsonl`` (single-writer
invariant).
"""
from __future__ import annotations

import json
from pathlib import Path

from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionRequest,
)


class JsonlRequestSink:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def emit(self, request: DecisionRequest) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(request.to_contract(), ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
