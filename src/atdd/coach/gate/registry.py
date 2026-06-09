"""The per-transition gate-check registry (#1020 scope B).

Replaces the single ``pre_commit_gate`` string with a LIST of declared checks
per transition. Other issues register INTO the module-level ``GATE_REGISTRY``
seam rather than hand-editing ``issue_lifecycle.py``:

    from atdd.coach.gate.registry import GATE_REGISTRY
    GATE_REGISTRY.register("PLANNED", "RED", MyStructuralCheck())   # e.g. #958

MIGRATION SAFETY (scope E): ``GATE_REGISTRY`` ships EMPTY. With no registered
checks, ``evaluate_transition_gate`` is a no-op for every transition, so flipping
the gate from advisory to blocking cannot make any existing transition start
failing. #958/#1017 add the real blocking checks later.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from atdd.coach.gate.decision import GateCheck


class GateRegistry:
    """Maps a ``(from_phase, to_phase)`` transition to its list of gate checks."""

    def __init__(self) -> None:
        self._checks: Dict[Tuple[str, str], List[GateCheck]] = {}

    def register(self, from_phase: str, to_phase: str, check: GateCheck) -> None:
        """Register a check to run on the ``from_phase -> to_phase`` transition."""
        self._checks.setdefault((from_phase, to_phase), []).append(check)

    def checks_for(self, from_phase: str, to_phase: str) -> List[GateCheck]:
        """Return the checks registered for a transition (a copy; never None)."""
        return list(self._checks.get((from_phase, to_phase), ()))

    def clear(self, from_phase: str, to_phase: str) -> None:
        """Remove all checks registered for a transition (test isolation)."""
        self._checks.pop((from_phase, to_phase), None)

    def is_empty(self) -> bool:
        """True when no checks are registered for any transition.

        An empty registry can never block (gated-but-unregistered transitions
        proceed), so callers can short-circuit the whole gate — and skip the
        issue fetch — while the registry is empty (the shipped default).
        """
        return not any(self._checks.values())


# The shipped registry — EMPTY by default (migration safety, scope E).
GATE_REGISTRY = GateRegistry()
