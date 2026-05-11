# URN: component:observe-and-correct:observer-runtime-and-rules:canonical_naming_drift:backend:application
# Runtime: python
# Purpose: Observer rule 14 — detect multiplexer surface name drift; re-apply canonical via babysit.correct_naming_drift.

"""Observer rule 14 — ``coach.observer.canonical-naming-drift`` (spec §8.3).

Absorbs ``babysit.correct_naming_drift`` verbatim per spec §0.2. The
canonical-name source of truth is ``session_naming.is_canonical_name`` /
``compute_canonical_name``. The rule fires per tick when any
``surface_state`` event in :class:`ObservedInput.events` carries a name
that fails ``is_canonical_name``.

The structured ``surface_state`` event shape (consumed by both the
predicate and ``apply_correction``) is::

    {
        "type": "surface_state",
        "ref": "<multiplexer surface ref>",
        "name": "<current name on the surface>",
        "expected_canonical": "<the canonical name to re-apply>",
    }

The ``expected_canonical`` field is what babysit's caller computes from
``orchestrate-state.json::canonical_name`` (or
``compute_canonical_name`` as a fallback) — pre-resolving it here keeps
the predicate pure.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

from atdd.coach.commands import observer
from atdd.coach.commands._archived.babysit import correct_naming_drift
from atdd.coach.utils.session_naming import is_canonical_name


_RULE_ID = "coach.observer.canonical-naming-drift"
_CORRECTION_TEXT = (
    "Multiplexer surface name has drifted from canonical — re-apply per "
    "session_naming.format. See coach.orchestration.canonical-session-name."
)


def _surface_state_events(ctx: observer.ObservedInput) -> Iterable[Dict[str, Any]]:
    for ev in ctx.events or ():
        if isinstance(ev, dict) and ev.get("type") == "surface_state":
            yield ev


def predicate(ctx: observer.ObservedInput) -> bool:
    """True when any observed surface name is not canonical."""
    for ev in _surface_state_events(ctx):
        name = ev.get("name") or ""
        if not is_canonical_name(name):
            return True
    return False


def apply_correction(
    ctx: observer.ObservedInput,
    *,
    backend: Any,
    log_path: Path,
    applied_cache: Dict[str, str],
) -> None:
    """Side-effect path that calls babysit.correct_naming_drift verbatim.

    Iterates each ``surface_state`` event and re-applies the canonical
    name when drift is detected. Already-canonical surfaces are skipped
    by the underlying ``correct_naming_drift`` (idempotent within one run
    via ``applied_cache``).
    """
    for ev in _surface_state_events(ctx):
        ref = ev.get("ref") or ""
        name = ev.get("name") or ""
        expected = ev.get("expected_canonical") or ""
        if not ref or not expected:
            continue
        if is_canonical_name(name) and name == expected:
            continue
        correct_naming_drift(
            backend, ref, expected, applied_cache, log_path=log_path,
        )


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
    "correct_naming_drift",
    "is_canonical_name",
    "predicate",
]
