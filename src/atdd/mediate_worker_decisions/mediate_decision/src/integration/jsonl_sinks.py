"""VerdictSink / EscalationSink adapters — append the contract as one JSONL line."""
from __future__ import annotations

import json
from pathlib import Path

from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    Escalation,
    Verdict,
)


class _JsonlSink:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def _append(self, record: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


class JsonlVerdictSink(_JsonlSink):
    def emit(self, verdict: Verdict) -> None:
        self._append(verdict.to_contract())


class JsonlEscalationSink(_JsonlSink):
    def emit(self, escalation: Escalation) -> None:
        self._append(escalation.to_contract())
