"""Role-aware canonical managed-surface naming — ``coach.session.canonical-role-name``.

Rehomed from `atdd.coach.observer_rules.canonical_role_naming` (#1486). That module
mixed this pure recognition predicate with the observer's rule machinery
(``ObserverRule`` / ``ObservedInput`` / drift correction); the observer was
decommissioned with the coach's sub-worker orchestration verbs, but the *rule*
survives — it is declared in ``session.convention.yaml`` and bound by
``coach/validators/test_canonical_role_naming.py``.

Recognition was previously delegated to the domain primitive
``enforce_surface_conformance...canonical_name.is_role_aware_name``. That wagon
(``consolidate-coach-workspace``) was pruned with the coach's sub-worker
orchestration, so the predicate is inlined here — this module is now the single
source of truth for the shape, and there is still no second regex.

Only the recognition half came across. The builder/sanitizer half
(``build_role_aware_name`` / ``sanitize_slug``) had zero consumers repo-wide and
pulled ``domain/role.py`` plus ``coach.utils.session_naming``, so it was dropped
rather than ported as dead code.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

RULE_ID = "coach.session.canonical-role-name"

# Role-aware canonical name: ``<REPO><N>[-phase<M>]-<role>-<slug>`` with role in
# {worker, coach-daemon, observer}. The role alternation sits between the optional
# phase infix and the slug, so an unknown role token never matches — the role is
# never guessed. Mirrors contracts/commons/coach/canonical-surface-name.schema.json.
ROLE_AWARE_NAME_REGEX = re.compile(
    r"^([A-Z]{2,8})(\d+)(-phase\d+)?-(worker|coach-daemon|observer)-"
    r"([a-z0-9]+(?:-[a-z0-9]+)*)$"
)


def is_conforming(name: str) -> bool:
    """True when ``name`` is a role-aware canonical managed-surface name."""
    if not isinstance(name, str):
        return False
    return ROLE_AWARE_NAME_REGEX.match(name.strip()) is not None


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
    "ROLE_AWARE_NAME_REGEX",
    "RULE_ID",
    "flag_non_conforming",
    "is_conforming",
]
