"""AnsweredSet — pure idempotency set over request_ids (WMBT E005).

The daemon marks every request_id it has answered or escalated so it never acts
on the same blocked item twice. The set is seeded at startup from the durable
verdicts.jsonl + escalations.jsonl ledgers (re-hydration), so idempotency holds
across a process restart as well as within a single run.
"""
from __future__ import annotations

from typing import Iterable, Set


class AnsweredSet:
    def __init__(self, seed: Iterable[str] = ()) -> None:
        self._seen: Set[str] = {r for r in seed if r}

    def seen(self, request_id: str) -> bool:
        return request_id in self._seen

    def mark(self, request_id: str) -> None:
        if request_id:
            self._seen.add(request_id)

    def __len__(self) -> int:
        return len(self._seen)

    def __contains__(self, request_id: str) -> bool:
        return request_id in self._seen
