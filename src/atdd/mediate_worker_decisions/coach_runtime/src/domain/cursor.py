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
    """Return the first record past `cursor` and the advanced cursor.

    `cursor` is a count of already-handled records. A negative cursor is
    clamped to 0. At (or past) the end of the ledger no record is returned and
    the cursor is left unchanged, so a caller never advances past an escalation
    it did not actually surface.
    """
    if cursor < 0:
        cursor = 0
    if cursor < len(records):
        return records[cursor], cursor + 1
    return None, cursor
