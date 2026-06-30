# Component: component:atdd-plan-core:confirm-gate:InterlockingSanity:backend:application
"""Confirm-gate interlocking sanity (#1249, parent #1246).

``planner.plan.confirm-requires-interlocking-sanity``: ``atdd plan`` Confirm must
not lock a train-bearing plan when a kept train unit's interlocking is unsound.
This module is the gate body invoked by ``PlanSession.confirm`` *before* it sets
``locked = True`` — so any failure leaves the session unlocked (atomicity).

It calls the stable #1248 Python API (``load_interlocking`` / ``validate_interlocking``)
and the #1249 ``sanity`` checks directly — never shelling out. It fails **closed**:
a missing/unsound interlocking, an unresolvable reference, or an unexpected crash
in the validators all raise :class:`SessionGateError`. A kept train unit that
declares no interlocking is a direct train and is allowed (no policy requires one).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from atdd.planner.interlocking import (
    InterlockingError,
    load_interlocking,
    validate_interlocking,
)
from atdd.planner.interlocking import sanity
from atdd.planner.interlocking.discovery import interlocking_home

__all__ = ["GateFailure", "assert_kept_train_interlocking_sanity"]


class GateFailure(Exception):
    """Internal carrier of one failed-gate evidence row (translated to a
    SessionGateError by the caller)."""

    def __init__(self, rows: List[dict]):
        self.rows = rows
        super().__init__(f"{len(rows)} interlocking sanity failure(s)")


def _interlocking_ref(unit: dict) -> Optional[dict]:
    """Return the unit's declared interlocking reference, or None for a direct
    train. Accepts ``spec.source_interlocking`` (the #1248 train back-ref shape)
    or a bare ``spec.interlocking`` string."""
    spec = unit.get("spec") or {}
    ref = spec.get("source_interlocking") or spec.get("interlocking")
    if ref is None:
        return None
    if isinstance(ref, str):
        return {"interlocking_id": ref}
    if isinstance(ref, dict):
        return ref
    return None


def _resolve_path(interlocking_id: str, root: Path) -> Path:
    slug = interlocking_id.split(":", 1)[-1]
    return interlocking_home(root) / f"{slug}.yaml"


def _evidence_rows(session_id: str, train_ref: str, il_id: str,
                   found: "dict[str, list[dict]]", semantic: list) -> List[dict]:
    rows: List[dict] = []
    for rule_id, evlist in found.items():
        for ev in evlist:
            rows.append({"session_id": session_id, "train_id": train_ref,
                         "interlocking_id": ev.get("interlocking_id", il_id),
                         "route_id": ev.get("route_id"), "failed_rule": rule_id})
    for v in semantic:
        rows.append({"session_id": session_id, "train_id": train_ref,
                     "interlocking_id": il_id, "route_id": None,
                     "failed_rule": getattr(v, "rule_id", "PLAN-INTERLOCKING")})
    return rows


def assert_kept_train_interlocking_sanity(session, root: Path | str = ".") -> None:
    """Raise :class:`SessionGateError` if any kept train unit's interlocking is
    unsound. No kept train units (or all direct trains) -> returns silently."""
    from atdd.planner.commands.plan_session import SessionGateError

    root = Path(root)
    failures: List[dict] = []
    for unit in session.kept_units():
        if unit.get("kind") != "train":
            continue
        ref = _interlocking_ref(unit)
        if ref is None:
            continue  # direct train — no interlocking policy requires one
        il_id = ref.get("interlocking_id") or ""
        train_ref = unit.get("ref", "")
        try:
            il = load_interlocking(_resolve_path(il_id, root))
            found = sanity.interlocking_violations(il, root)
            semantic = validate_interlocking(il, root)
        except InterlockingError as exc:
            # missing / shape-invalid interlocking -> fail closed.
            raise SessionGateError(
                f"confirm-requires-interlocking-sanity: kept train {train_ref!r} "
                f"references interlocking {il_id!r} that could not be loaded: {exc}"
            ) from exc
        except Exception as exc:  # fail closed on a validator crash (#1249)
            raise SessionGateError(
                f"confirm-requires-interlocking-sanity: interlocking sanity for "
                f"{il_id!r} crashed; failing closed: {exc!r}"
            ) from exc
        if found or semantic:
            failures.extend(_evidence_rows(session.session_id, train_ref, il_id,
                                           found, semantic))

    if failures:
        raise SessionGateError(
            "confirm-requires-interlocking-sanity: cannot lock a train-bearing plan "
            f"with {len(failures)} interlocking sanity failure(s): {failures}"
        )
