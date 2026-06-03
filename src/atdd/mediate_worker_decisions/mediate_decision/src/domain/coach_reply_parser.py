"""Pure parser for the coach's ``DECISION:`` / ``REASON:`` reply (no I/O).

A well-formed reply yields a (selected_option_id, reason) pair; a reply without
a DECISION token raises ``CoachReplyParseError`` rather than guessing a verdict
(WMBT E001).
"""
from __future__ import annotations

import re
from typing import Iterable, Tuple

_DECISION_RE = re.compile(r"DECISION:\s*([A-Za-z0-9_.-]+)", re.IGNORECASE)
_REASON_RE = re.compile(r"REASON:\s*(.+)", re.IGNORECASE)


class CoachReplyParseError(Exception):
    """Raised when the coach reply carries no parseable DECISION token."""


def parse_reply(text: str) -> Tuple[str, str]:
    decision = _DECISION_RE.search(text or "")
    if not decision:
        raise CoachReplyParseError("no DECISION token in coach reply")
    reason_m = _REASON_RE.search(text)
    reason = reason_m.group(1).strip() if reason_m else ""
    return decision.group(1).strip(), reason


def selection_in_options(decision_id: str, option_ids: Iterable[str]) -> bool:
    """True iff the coach's selected option id is one offered to the worker (WMBT Y001)."""
    return decision_id in set(option_ids)
