"""DecisionLedger adapter: append the record contract as one JSONL line.

Writes to the bridge's own ``.atdd/decision/decisions.jsonl`` namespace rather
than reusing ``JsonlPersistenceStore.append_decision`` directly — that method is
typed to the coach state machine's ``TransitionDecision`` and would pull the
coach transition vocabulary into this feature. Keeping a sibling stream also
avoids single-writer contention with an active coach run's decisions log.
"""
from __future__ import annotations

from pathlib import Path

from atdd.mediate_worker_decisions.apply_decision.src.domain.record import DecisionRecord
from atdd.mediate_worker_decisions.commons.jsonl_writer import append_jsonl


class JsonlDecisionLedger:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def record(self, record: DecisionRecord) -> None:
        append_jsonl(self._path, record.to_contract())
