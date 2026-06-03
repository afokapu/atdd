"""Presentation seam for mediate-decision.

Thin: turns the use case outcome into the external artifact kind so a CLI/runner
can route a request line to a verdict or an escalation.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    Escalation,
    Verdict,
)


def outcome_kind(outcome: object) -> str:
    if isinstance(outcome, Verdict):
        return "verdict"
    if isinstance(outcome, Escalation):
        return "escalation"
    raise TypeError(f"unexpected mediate outcome: {type(outcome)!r}")
