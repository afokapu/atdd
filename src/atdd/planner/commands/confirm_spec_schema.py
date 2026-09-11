# Component: component:atdd-plan-core:confirm-gate:SpecSchema:backend:application
"""Confirm-gate spec schema + granularity enforcement (#1929).

``planner.plan.spec-is-schema-valid`` / ``planner.plan.granularity-completeness``:
the Ratify half of the spec gate. Compose already refused anything WRONG (a value
present and mis-shaped); this is where COMPLETENESS is added — ``required``,
``minItems``, ``minLength`` — over the kept units, and where the granularity
ladder is reported.

This is the gate body invoked by ``PlanSession.confirm`` *before* it sets
``locked = True``, so any failure leaves the session unlocked (atomicity),
mirroring the interlocking-sanity (#1249), verb-object (#1276) and
artifact-naming (#1329) gates it sits beside — and living in its own module for
the same reason they do.

Only ENFORCED kinds raise. An advisory kind's findings are refreshed onto the
unit so ``atdd plan show`` and the Ratify warning can read them; they never
block, because the schemas behind them do not describe the artifacts atdd
authors today (see :mod:`atdd.planner.commands.plan_unit_schema`).
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from atdd.coach.utils.config import load_atdd_config
from atdd.planner.commands.plan_unit_schema import check_unit_spec

__all__ = ["GRANULARITY_LADDER", "assert_kept_specs_schema_valid", "granularity_report"]

#: The rungs of the granularity ladder a decomposition descends. A plan that
#: keeps wagons and nothing else has named a shape but nothing testable.
GRANULARITY_LADDER = ("wagon", "feature", "wmbt", "acceptance")


def assert_kept_specs_schema_valid(session, root: Path | str = ".") -> None:
    """Raise :class:`SessionGateError` unless every kept unit's spec would author
    a schema-valid artifact. Advisory kinds record instead of raising."""
    from atdd.planner.commands.plan_session import SessionGateError

    config = load_atdd_config(Path(root))
    blocking: List[str] = []
    for unit in session.kept_units():
        tier, findings = check_unit_spec(
            unit["kind"], unit.get("spec") or {}, config=config, stage="ratify")
        if not findings:
            unit.pop("advisories", None)
            continue
        if tier == "enforce":
            blocking += [f"{unit['kind']} {unit['ref']}: {f}" for f in findings]
        else:
            unit["advisories"] = findings

    if blocking:
        raise SessionGateError(
            "spec-is-schema-valid: cannot lock a plan whose kept units would "
            "author schema-invalid artifacts:\n  - " + "\n  - ".join(blocking))


def granularity_report(session) -> dict:
    """Which rungs of the ladder the kept decomposition reached.

    Reports; never blocks. A plan session must allow incremental composition —
    ``local-scope`` scopes each run to a slice, so requiring every rung before an
    operator may look at eight wagons would make the session unusable. The caller
    decides what to do with a dangling ladder: the CLI warns, ``--strict``
    refuses.
    """
    kept: dict = {}
    for unit in session.kept_units():
        kept[unit["kind"]] = kept.get(unit["kind"], 0) + 1
    return {
        "kept": kept,
        "reached": [k for k in GRANULARITY_LADDER if kept.get(k)],
        "dangling": [k for k in GRANULARITY_LADDER if not kept.get(k)],
        "advisories": sum(
            len(u.get("advisories") or []) for u in session.kept_units()
        ),
    }
