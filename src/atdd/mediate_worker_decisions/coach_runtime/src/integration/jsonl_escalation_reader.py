"""Ledger tail + durable cursor for the notify pass (integration).

``JsonlEscalationReader`` reads the daemon's append-only escalations.jsonl into
a list of records (malformed/blank lines skipped — a partial ledger never
crashes the wait). ``FileCursorStore`` persists the read offset as a single
integer next to the ledger, so a handled escalation is never re-emitted across
``atdd coach wait`` invocations.

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from atdd.mediate_worker_decisions.coach_runtime.src.log import log as _log


class JsonlEscalationReader:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def read_all(self) -> List[dict]:
        """Every escalation record appended so far; blank/malformed lines skipped."""
        if not self._path.exists():
            return []
        records: List[dict] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a partial ledger never crashes the wait
        return records


class FileCursorStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def load(self) -> int:
        if not self._path.exists():
            return 0
        try:
            return int(self._path.read_text(encoding="utf-8").strip() or 0)
        except (ValueError, OSError) as exc:
            _log.debug(
                "cursor file unreadable; restarting at 0",
                extra={"path": str(self._path), "error": str(exc)},
            )
            return 0

    def save(self, cursor: int) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(str(int(cursor)), encoding="utf-8")
        os.replace(tmp, self._path)  # atomic — cursor never half-written
