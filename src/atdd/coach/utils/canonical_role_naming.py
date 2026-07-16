"""Role-aware canonical managed-surface naming — ``coach.session.canonical-role-name``.

Rehomed from `atdd.coach.observer_rules.canonical_role_naming` (#1486). That module
mixed this pure recognition predicate with the observer's rule machinery
(``ObserverRule`` / ``ObservedInput`` / drift correction); the observer was
decommissioned with the coach's sub-worker orchestration verbs, but the *rule*
survives — it is declared in ``session.convention.yaml`` and bound by
``coach/validators/test_canonical_role_naming.py``.

Recognition itself is the domain primitive
``enforce_surface_conformance...canonical_name.is_role_aware_name`` — single source
of truth, no second regex.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.canonical_name import (
    is_role_aware_name,
)

RULE_ID = "coach.session.canonical-role-name"


def is_conforming(name: str) -> bool:
    """True when ``name`` is a role-aware canonical managed-surface name."""
    return is_role_aware_name(name)


def flag_non_conforming(events: Iterable[Dict[str, Any]]) -> List[str]:
    """Return the refs of managed surfaces whose name is not role-aware canonical."""
    flagged: List[str] = []
    for ev in events:
        if ev.get("type") != "surface_state":
            continue
        name = ev.get("name") or ""
        ref = ev.get("ref") or ""
        if ref and not is_conforming(name):
            flagged.append(ref)
    return flagged


__all__ = [
    "RULE_ID",
    "flag_non_conforming",
    "is_conforming",
]
