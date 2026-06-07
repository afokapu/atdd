# URN: component:observe-and-correct:observer-runtime-and-rules:layout_drift:backend:application
# Runtime: python
# Purpose: Observer rule 15 — detect surface count or arrangement drift; re-apply via babysit.correct_layout_drift.

"""Observer rule 15 — ``coach.observer.layout-drift`` (spec §8.3).

The corrector is ``detectors.correct_layout_drift``. The canonical-layout
source of truth is ``session_naming.target_grid_label``.

The structured ``layout_state`` event shape (consumed by both predicate
and ``apply_correction``) is::

    {
        "type": "layout_state",
        "surface_count": <int>,
        "last_target": "<the layout label currently applied>",
    }

The predicate fires when the current ``surface_count`` resolves to a
``target_grid_label`` that differs from the cached ``last_target`` —
i.e., the layout band has changed since the last tick and a re-apply
is needed. Conforming arrangements (cache matches the current target)
do not fire.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

from atdd.coach.commands import observer
from atdd.coach.observer_rules.detectors import correct_layout_drift
from atdd.coach.utils.session_naming import target_grid_label


_RULE_ID = "coach.observer.layout-drift"
_CORRECTION_TEXT = (
    "Multiplexer layout has drifted from the canonical grid — re-apply per "
    "layout_placement.policy. See coach.session.layout-conformance."
)


def _layout_state_events(ctx: observer.ObservedInput) -> Iterable[Dict[str, Any]]:
    for ev in ctx.events or ():
        if isinstance(ev, dict) and ev.get("type") == "layout_state":
            yield ev


def predicate(ctx: observer.ObservedInput) -> bool:
    """True when the observed surface count resolves to a target band that
    differs from the currently-applied ``last_target``."""
    for ev in _layout_state_events(ctx):
        count = ev.get("surface_count")
        last = ev.get("last_target") or ""
        if not isinstance(count, int):
            continue
        target = target_grid_label(count)
        if target != last:
            return True
    return False


def apply_correction(
    ctx: observer.ObservedInput,
    *,
    log_path: Path,
    layout_cache: Dict[str, str],
) -> bool:
    """Side-effect path that calls ``detectors.correct_layout_drift``.

    Returns True when a re-apply was actually issued (i.e.,
    ``correct_layout_drift`` returned True), False when the layout band
    was already conforming (idempotent).
    """
    fired_any = False
    for ev in _layout_state_events(ctx):
        count = ev.get("surface_count")
        if not isinstance(count, int):
            continue
        if correct_layout_drift(count, layout_cache, log_path=log_path):
            fired_any = True
    return fired_any


def build_rule() -> observer.ObserverRule:
    return observer.ObserverRule(
        rule_id=_RULE_ID,
        predicate=predicate,
        correction_text=_CORRECTION_TEXT,
        injection_method="cli-return",
        severity=2,
        disposition="advisory",
    )


__all__ = [
    "apply_correction",
    "build_rule",
    "correct_layout_drift",
    "predicate",
    "target_grid_label",
]
