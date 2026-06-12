"""Idempotent phase-label advance primitive (#1079, WMBT E032).

``_swap_phase_label`` (coach/commands/coach.py) unconditionally rewrites the
issue's ``atdd:<phase>`` labels every call. When the #1082 orchestrator re-fires
the advance (re-poll of done.json, warm-resume re-invocation) that churns the
label, double-advances, or silently overwrites an out-of-band change. This
primitive makes the advance self-checking: read the current phase first, then
no-op when already at the target, swap exactly once when at the expected source,
and refuse when at an unexpected phase — so re-firing the same transition is
safe and double-invocation converges to one end state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PhaseAdvanceOutcome:
    """Outcome of an idempotent label advance the orchestrator branches on."""

    status: str  # "advanced" | "noop" | "refused"
    current: str
    expected: str


def advance_phase_label_idempotent(
    issue_number: int,
    source: str,
    target: str,
    *,
    read_phase: Callable[[int], str],
    swap_label: Callable[[int, str], None],
) -> PhaseAdvanceOutcome:
    """Advance ``issue_number`` from ``source`` to ``target`` idempotently.

    ``read_phase``/``swap_label`` are injected so the advance is unit-testable
    and decoupled from the live ``gh`` calls. The guard:

    * already at ``target`` → no-op (no mutation, no error);
    * at the expected ``source`` → exactly one swap to ``target``;
    * at any other phase → refuse (no mutation), recording current vs expected.
    """
    current = read_phase(issue_number)

    if current == target:
        return PhaseAdvanceOutcome(status="noop", current=current, expected=source)

    if current == source:
        swap_label(issue_number, target)
        return PhaseAdvanceOutcome(status="advanced", current=target, expected=source)

    return PhaseAdvanceOutcome(status="refused", current=current, expected=source)
