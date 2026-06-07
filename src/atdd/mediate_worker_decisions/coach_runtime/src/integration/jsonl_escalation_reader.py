"""Ledger tail + durable cursor for the notify pass (integration).

``JsonlEscalationReader`` reads the daemon's append-only escalations.jsonl into
a list of records (malformed/blank lines skipped — a partial ledger never
crashes the wait). ``FileCursorStore`` persists the read offset as a single
integer next to the ledger, so a handled escalation is never re-emitted across
``atdd coach wait`` invocations.

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations

from pathlib import Path
from typing import List


class JsonlEscalationReader:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def read_all(self) -> List[dict]:
        raise NotImplementedError("GREEN")


class FileCursorStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def load(self) -> int:
        raise NotImplementedError("GREEN")

    def save(self, cursor: int) -> None:
        raise NotImplementedError("GREEN")
