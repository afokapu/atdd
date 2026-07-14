# Component: component:atdd-plan-core:confirm-gate:VerbObjectNaming:backend:application
"""Confirm-gate verb-object naming enforcement (#1276).

``planner.wagon.name-is-verb-object`` / ``planner.feature.name-is-verb-object``:
``atdd plan`` Confirm must not lock a plan whose kept wagon/feature units carry a
non-verb-object slug. This is the gate body invoked by ``PlanSession.confirm``
*before* it sets ``locked = True`` — so any failure leaves the session unlocked
(atomicity), mirroring the interlocking-sanity gate.

It uses the pure :func:`atdd.planner.naming.is_verb_object` mechanic and the
explicit verb lexicon + brand exceptions defined in the conventions. Only kept
``wagon``/``feature`` units are checked; other unit kinds are ignored.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from atdd.planner.naming import is_verb_object

__all__ = ["assert_kept_wagon_feature_naming"]


def _unit_naming_failure(unit) -> "str | None":
    """The verb-object complaint for one kept unit, or None when it names nothing
    authorable (nothing to check) or its name is well-formed."""
    kind = unit.get("kind")
    spec = unit.get("spec") or {}
    if kind == "wagon":
        raw = spec.get("wagon")
        if not raw:
            return None
        slug = raw.split(":", 1)[-1] if raw.startswith("wagon:") else raw
        ok, reason = is_verb_object(slug, artifact="wagon")
        return None if ok else f"wagon:{slug} — {reason}"
    if kind == "feature":
        urn = spec.get("urn")
        if not urn:
            return None
        ok, reason = is_verb_object(urn.split(":")[-1], artifact="feature")
        return None if ok else f"{urn} — {reason}"
    return None


def assert_kept_wagon_feature_naming(session, root: Path | str = ".") -> None:
    """Raise :class:`SessionGateError` if any kept wagon/feature unit carries a
    non-verb-object name in its author spec. The check reads the *authorable* name
    from the unit ``spec`` (``spec.wagon`` for a wagon, ``spec.urn`` for a feature)
    — exactly what ``atdd author`` would write — and is a no-op for a unit whose
    spec carries no name (nothing to author a name from; author-input validation
    polices a missing/malformed spec downstream). No offending units -> returns
    silently."""
    from atdd.planner.commands.plan_session import SessionGateError

    failures: List[str] = []
    for unit in session.kept_units():
        failure = _unit_naming_failure(unit)
        if failure is not None:
            failures.append(failure)

    if failures:
        raise SessionGateError(
            "name-is-verb-object: cannot lock a plan with non-verb-object artifact "
            f"name(s): {failures}"
        )
