# URN: component:plan:train-interlocking:RouteSpace:backend:application
# Runtime: python
# Purpose: Planner-time route-space admission + category assessment over the train registry (#1554).
"""Route-space admission and category assessment (issue #1554).

The malformed WMBT that started this program was not a WMBT-shape failure. It was
an **omitted-route** failure that propagated downward until the missing route
outcome was forced into the wrong acceptance set. This module enforces that class
of defect at the altitude it occurs: *planning*.

Two rules live here.

``planner.train.route-space-admission`` (repo-level)
    Every registered train must satisfy EXACTLY ONE of:

      * it is targeted by exactly one registered interlocking route, or
      * it declares a typed single-route assessment (``route_space``).

    The point is that **absence stops meaning ``direct``**. Silence used to read
    as a positive assertion that route analysis had been performed and concluded
    single-route, which made an unanalysed train indistinguishable from a
    deliberately-classified one. The runtime may keep dispatching directly; what
    changes is that planner omission no longer implies analysis happened.

    This rule is evaluated over the ROUTE REGISTRY, not over the train's optional
    ``source_interlocking`` back-reference. That field is documented as *"Pure
    traceability — it must NOT alter train linearity and is NOT a second source of
    truth"*, so consulting it would duplicate the authoritative route -> train
    edge and invite exactly the drift the schema warns against. It is never read
    here.

``planner.train.route-category-assessment`` (per-interlocking)
    Each category in the closed set is assessed individually: ``nominal``
    requires one or more routes, and ``alternate``/``error``/``exception`` require
    routes or a typed not-applicable. A floor of "at least one non-nominal route"
    is gamed by adding a token alternate while error and exception behaviour go
    unwritten, so each category is judged on its own.

Both vocabularies are CLOSED. A free-text reason is an escape hatch that erodes —
it gets copy-pasted until every subject carries one — so a basis is an enum the
way WMBT dimension and lens are enums. The strongest basis,
``discharged-by-residual``, discharges a category through a declared residual,
and every residual must carry a reason, an acceptance_ref and a validator_ref
(``planner.train.interlocking-structural-residual-explicit``). Discharging a
category therefore costs a bound obligation rather than a sentence.

Stdlib + yaml only; no other-layer imports (boundaries §3.3).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from .discovery import iter_interlocking_paths
from .models import TrainInterlocking

_log = logging.getLogger(__name__)

__all__ = [
    "CATEGORIES",
    "NOMINAL",
    "DISCHARGEABLE_CATEGORIES",
    "SINGLE_ROUTE_BASES",
    "NOT_APPLICABLE_BASES",
    "TRAIN_REGISTRY_PATH",
    "registered_trains",
    "route_targets",
    "route_space_admission_violations",
    "category_assessment_violations",
]

TRAIN_REGISTRY_PATH = "plan/_trains.yaml"

NOMINAL = "nominal"
#: The closed category space. Every one of these is assessed; none may be silently
#: omitted. Ordered nominal-first so evidence reads in escalation order.
CATEGORIES: Tuple[str, ...] = ("nominal", "alternate", "error", "exception")
#: ``nominal`` is the executed path and can never be typed not-applicable.
DISCHARGEABLE_CATEGORIES: Tuple[str, ...] = tuple(c for c in CATEGORIES if c != NOMINAL)

#: Closed vocabulary for ``train.route_space.basis``.
SINGLE_ROUTE_BASES: Tuple[str, ...] = (
    "sole-terminal-outcome",
    "externally-routed",
    "not-yet-assessed",
)
#: Closed vocabulary for ``interlocking.category_assessment.<category>.basis``.
NOT_APPLICABLE_BASES: Tuple[str, ...] = (
    "discharged-by-residual",
    "outcome-cannot-arise",
    "not-yet-assessed",
)

_TRANSITIONAL = "not-yet-assessed"


# ---------------------------------------------------------------------------
# registry readers
# ---------------------------------------------------------------------------
def _read_yaml(path: Path) -> dict:
    """Parse a YAML mapping, returning ``{}`` when absent or unparseable.

    Parse failures are owned by the schema/loader family, not by these rules, so
    they degrade to "nothing declared" here rather than masquerading as a
    route-space violation.
    """
    if not path.is_file():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        _log.debug(
            "route-space skipped (unparseable yaml)",
            extra={"path": str(path), "error": str(exc).splitlines()[0][:120]},
        )
        return {}
    return doc if isinstance(doc, dict) else {}


def registered_trains(root: Path | str) -> Tuple[dict, ...]:
    """Every entry of the ``plan/_trains.yaml`` registry, flattened.

    The registry nests theme -> bucket -> entries (issue #1421). Each returned
    dict is the registry entry itself; ``path`` locates the per-train document
    that carries the ``route_space`` declaration.
    """
    registry = _read_yaml(Path(root) / TRAIN_REGISTRY_PATH).get("trains") or {}
    if not isinstance(registry, dict):
        # The legacy list shape was retired by #1421 and is rejected loudly at the
        # authoring seam; here it simply declares no trains.
        return ()
    out: List[dict] = []
    for buckets in registry.values():
        if not isinstance(buckets, dict):
            continue
        for entries in buckets.values():
            if not isinstance(entries, list):
                continue
            out.extend(e for e in entries if isinstance(e, dict) and e.get("train_id"))
    return tuple(out)


def route_targets(root: Path | str) -> Dict[str, List[Tuple[str, str]]]:
    """``train_id -> [(interlocking_id, route_id), ...]`` over every interlocking.

    This is the AUTHORITATIVE route -> train edge. It is read from the
    interlocking documents under the canonical home and never from a train's
    optional ``source_interlocking`` back-reference.

    Loading is deliberately raw (``yaml`` rather than ``load_interlocking``): an
    interlocking that fails shape validation is caught by the loader/schema rules,
    and route-space admission must not go silently blind to that document's routes
    just because some unrelated field is malformed. Failing blind here would
    re-create the exact omission this module exists to catch.
    """
    targets: Dict[str, List[Tuple[str, str]]] = {}
    for path in iter_interlocking_paths(root):
        doc = _read_yaml(path)
        iid = doc.get("interlocking_id") or str(path)
        for route in doc.get("routes") or []:
            if not isinstance(route, dict):
                continue
            train_id = route.get("train_id")
            if train_id:
                targets.setdefault(train_id, []).append((iid, route.get("route_id")))
    return targets


# ---------------------------------------------------------------------------
# rule 1: route-space admission (repo-level)
# ---------------------------------------------------------------------------
def _declared_route_space(entry: dict, root: Path) -> dict:
    """The ``route_space`` block from the per-train document (``{}`` when absent).

    The declaration lives on the train ARTIFACT, not on its registry entry, so the
    registry stays a thin index.
    """
    rel = entry.get("path")
    if not rel:
        return {}
    block = _read_yaml(root / rel).get("route_space")
    return block if isinstance(block, dict) else {}


# Admission outcome vocabulary. Hoisted to module level so the status names are
# a named, greppable vocabulary rather than literals buried in a branch — and so
# the complexity counter, which matches decision keywords as whole words over raw
# body text, no longer reads the `and` inside hyphenated names like
# `route-targeted-and-declared` as a boolean operator.
_MULTIPLY_ROUTED = "multiply-routed"
_ROUTED_AND_DECLARED = "route-targeted-and-declared"
_UNROUTED_UNDECLARED = "unrouted-and-undeclared"
_INVALID_CLASSIFICATION = "invalid-classification"
_INVALID_BASIS = "invalid-basis"
_NO_RETIRER = "transitional-without-retirer"


def _admission_status(hits: List[tuple], declared: dict) -> "str | None":
    """Classify ONE train's route-space admission; ``None`` when it is admitted.

    Split out from :func:`route_space_admission_violations` so the *judgement*
    (which of the mutually exclusive admission outcomes holds) is separable from
    the *evidence construction* around it.
    """
    if len(hits) > 1:
        # A train is a single linear path; two routes selecting it makes the
        # route -> train edge ambiguous.
        return _MULTIPLY_ROUTED

    if hits:
        # Route-targeted plus self-declared: two sources of truth about one
        # train's routing, which is what `source_interlocking` is explicitly
        # forbidden from becoming.
        return _ROUTED_AND_DECLARED if declared else None

    # No route. Silence is no longer an assertion that analysis happened.
    if not declared:
        return _UNROUTED_UNDECLARED
    if declared.get("classification") != "single-route":
        return _INVALID_CLASSIFICATION

    basis = declared.get("basis")
    if basis not in SINGLE_ROUTE_BASES:
        return _INVALID_BASIS
    if basis == _TRANSITIONAL and not declared.get("retires_with"):
        return _NO_RETIRER
    return None


def route_space_admission_violations(root: Path | str) -> List[dict]:
    """``planner.train.route-space-admission``: every registered train is
    route-targeted or typed single-route, and never both or neither."""
    root = Path(root)
    targets = route_targets(root)
    out: List[dict] = []

    for entry in registered_trains(root):
        hits = targets.get(entry["train_id"], [])
        declared = _declared_route_space(entry, root)
        status = _admission_status(hits, declared)
        if status is None:
            continue
        out.append({
            "train_id": entry["train_id"],
            "train_path": entry.get("path"),
            "route_ids": [f"{iid}::{rid}" for iid, rid in hits],
            "classification": declared.get("classification"),
            "basis": declared.get("basis"),
            "admission_status": status,
        })

    return out


# ---------------------------------------------------------------------------
# rule 2: category assessment (per-interlocking)
# ---------------------------------------------------------------------------
def category_assessment_violations(
    il: TrainInterlocking, root: Path | str = None
) -> List[dict]:
    """``planner.train.route-category-assessment``: every category is covered by
    routes or by a typed not-applicable.

    ``nominal`` requires routes and can never be discharged. Declaring an
    assessment for a category that already carries routes is a contradiction, so
    a stale not-applicable cannot outlive the gap it described.
    """
    routes_by_category = il.routes_by_category()
    assessments = il.assessment_index()
    residuals = il.residual_ids()
    out: List[dict] = []

    for category in CATEGORIES:
        route_ids = routes_by_category.get(category, [])
        assessment = assessments.get(category)

        evidence = {
            "interlocking_id": il.interlocking_id,
            "category": category,
            "route_ids": route_ids,
            "not_applicable_basis": assessment.basis if assessment else None,
        }

        if route_ids:
            if assessment:
                out.append({**evidence, "assessment_status": "routed-and-discharged"})
            continue

        # No routes for this category.
        if category == NOMINAL:
            # nominal is the executed path — a basis is never accepted for it.
            out.append({**evidence, "assessment_status": "nominal-unrouted"})
            continue
        if assessment is None:
            out.append({**evidence, "assessment_status": "unassessed"})
            continue
        if assessment.basis not in NOT_APPLICABLE_BASES:
            out.append({**evidence, "assessment_status": "invalid-basis"})
            continue
        if assessment.basis == "discharged-by-residual":
            if not assessment.residual_ref:
                out.append({**evidence, "assessment_status": "discharge-without-residual"})
            elif assessment.residual_ref not in residuals:
                out.append({**evidence, "assessment_status": "discharge-residual-undeclared"})
            continue
        if assessment.basis == _TRANSITIONAL and not assessment.retires_with:
            out.append({**evidence, "assessment_status": "transitional-without-retirer"})

    return out
