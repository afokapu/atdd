"""VerdictSink / EscalationSink adapters — append each contract as one JSONL line."""
from __future__ import annotations

from pathlib import Path

from atdd.mediate_worker_decisions.commons.jsonl_writer import append_jsonl
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    Escalation,
    Verdict,
)


class JsonlVerdictSink:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def emit(self, verdict: Verdict) -> None:
        append_jsonl(self._path, verdict.to_contract())


class JsonlEscalationSink:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def emit(self, escalation: Escalation) -> None:
        append_jsonl(self._path, escalation.to_contract())
