# URN: component:observe-and-correct:observer-runtime-and-rules:canonical_role_naming:backend:application
# Runtime: python
# Purpose: Role-aware extension of the canonical-naming-drift family (#865) — recognise/flag managed surface names lacking the <role> segment.

"""Role-aware canonical-naming drift (issue #865) — ``coach.session.canonical-role-name``.

Extends the canonical-naming-drift family (it reuses the same observer machinery
and the ``detectors.correct_naming_drift`` corrector) rather than forking it: this
module adds the role-aware recognition for coach-managed surfaces named
``<REPO><N>[-phase<M>]-<role>-<slug>`` (role ∈ worker | coach-daemon | observer).
The recognition itself is the pure domain primitive
``enforce_surface_conformance...canonical_name.is_role_aware_name`` — single source
of truth, no second regex.

Consumes the same ``surface_state`` event shape as
:mod:`atdd.coach.observer_rules.canonical_naming_drift`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

from atdd.coach.commands import observer
from atdd.coach.observer_rules.detectors import correct_naming_drift
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.canonical_name import (
    is_role_aware_name,
)

_RULE_ID = "coach.session.canonical-role-name"
_CORRECTION_TEXT = (
    "Coach-managed surface name lacks the role-aware canonical shape "
    "(<REPO><N>[-phase<M>]-<role>-<slug>). Re-apply per session_naming.format. "
    "See coach.session.canonical-role-name (#865)."
)


def is_conforming(name: str) -> bool:
    """True when ``name`` is a role-aware canonical managed-surface name."""
    return is_role_aware_name(name)


def _surface_state_events(ctx: observer.ObservedInput) -> Iterable[Dict[str, Any]]:
    for ev in ctx.events or ():
        if isinstance(ev, dict) and ev.get("type") == "surface_state":
            yield ev


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


def predicate(ctx: observer.ObservedInput) -> bool:
    """True when any observed managed surface name is not role-aware canonical."""
    for ev in _surface_state_events(ctx):
        if not is_conforming(ev.get("name") or ""):
            return True
    return False


def apply_correction(
    ctx: observer.ObservedInput,
    *,
    backend: Any,
    log_path: Path,
    applied_cache: Dict[str, str],
) -> None:
    """Re-apply the role-aware canonical name via the shared drift corrector."""
    for ev in _surface_state_events(ctx):
        ref = ev.get("ref") or ""
        name = ev.get("name") or ""
        expected = ev.get("expected_canonical") or ""
        if not ref or not expected:
            continue
        if is_conforming(name) and name == expected:
            continue
        correct_naming_drift(backend, ref, expected, applied_cache, log_path=log_path)


def build_rule() -> observer.ObserverRule:
    return observer.ObserverRule(
        rule_id=_RULE_ID,
        predicate=predicate,
        correction_text=_CORRECTION_TEXT,
        injection_method="cli-return",
        severity=3,
        disposition="advisory",
    )


__all__ = [
    "apply_correction",
    "build_rule",
    "flag_non_conforming",
    "is_conforming",
    "predicate",
]
