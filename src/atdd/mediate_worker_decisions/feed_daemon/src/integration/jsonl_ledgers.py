"""Durable JSONL ledgers + the human-escalation channel (MVP: jsonl + loud log).

``JsonlEscalationSink`` appends each escalation to escalations.jsonl (via the
wagon's single-writer ``append_jsonl``) AND emits a loud operator-visible WARNING
— that is the MVP human channel (DG-2). ``JsonlVerdictLedger`` appends each
auto-applied verdict to verdicts.jsonl. ``read_handled_request_ids`` reads both
ledgers to re-hydrate the answered-set on startup (WMBT E005, across restart).

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Set

from atdd.mediate_worker_decisions.commons.jsonl_writer import append_jsonl
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    Escalation,
    Verdict,
)

_LOG = logging.getLogger("atdd.feed_daemon")


class JsonlEscalationSink:
    def __init__(self, path: Path, logger: Optional[logging.Logger] = None) -> None:
        self._path = Path(path)
        self._log = logger or _LOG

    def record(self, escalation: Escalation) -> None:
        append_jsonl(self._path, escalation.to_contract())


class JsonlVerdictLedger:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def record(self, verdict: Verdict) -> None:
        append_jsonl(self._path, verdict.to_contract())


def read_handled_request_ids(*paths: Path) -> Set[str]:
    """Collect every request_id already recorded in the given ledger files.

    Used to re-hydrate the answered-set at startup (WMBT E005): a request_id
    present in verdicts.jsonl or escalations.jsonl was already handled, so the
    daemon must not act on it again after a restart. Malformed/blank lines are
    skipped — a partial ledger never crashes the daemon on boot.
    """
    handled: Set[str] = set()
    for path in paths:
        target = Path(path)
        if not target.exists():
            continue
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            request_id = record.get("request_id")
            if request_id:
                handled.add(request_id)
    return handled
