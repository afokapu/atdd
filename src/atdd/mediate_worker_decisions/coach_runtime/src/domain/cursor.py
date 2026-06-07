"""Pure cursor core for the coach-runtime notify pass (L006).

``next_escalation_after`` is the single pure decision: given an append-only list
of escalation records and a persisted read cursor (a count of already-handled
records), return the next unhandled record and the advanced cursor, or ``None``
and the unchanged cursor at end-of-ledger. No I/O, no clock — tested directly.

Skeleton: body lands in GREEN.
"""
from __future__ import annotations

from typing import List, Optional, Tuple


def next_escalation_after(
    records: List[dict], cursor: int
) -> Tuple[Optional[dict], int]:
    raise NotImplementedError("GREEN")
