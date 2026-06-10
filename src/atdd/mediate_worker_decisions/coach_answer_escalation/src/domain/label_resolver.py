"""Exact-label resolution for ``atdd coach answer`` (WMBT C009).

cmux's ``feed.question.reply`` returns ``delivered:true`` silently even when the
selections label matches NO real ``question_options[].label`` — the footgun that
stalls a worker (it stays parked while the operator believes the answer landed).
``resolve_exact_label`` resolves the operator's input to the EXACT option label
and raises ``LabelResolutionError`` LOUDLY on a mismatch or a partial/prefix
match — BEFORE any cmux reply is built — so the caller never trusts cmux's silent
delivered:true.

Skeleton: body lands in GREEN.
"""
from __future__ import annotations

from typing import Sequence


class LabelResolutionError(ValueError):
    """Raised when an operator input does not EXACTLY match an option label."""


def resolve_exact_label(operator_input: str, options: Sequence[str]) -> str:
    """Return the option label exactly equal to ``operator_input``.

    Exact match only — a partial/prefix/substring is rejected. Raises
    ``LabelResolutionError`` naming the invalid input and the valid options on any
    non-exact match, so the caller fails loudly instead of delivering a silent
    no-op reply.
    """
    raise NotImplementedError("wmbt:mediate-worker-decisions:C009")
