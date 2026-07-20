# URN: component:plan:train-interlocking:Models:backend:domain
# Runtime: python
# Purpose: Frozen value types for the train interlocking artifact (#1248 / #1246).
"""Typed, side-effect-free value types for the train interlocking artifact.

The interlocking is the train-domain *route-control* model: it is authoritative
for the guarded route space, while each route maps to exactly one linear train
variant (the runtime-executable path consumed by ``TrainRunner``). These
dataclasses are the mechanical substrate only — no IO, no business logic — so the
domain layer never imports from other layers (boundaries §3.3). Stdlib-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Entrypoint:
    """Declared reachability surface (so reachability is never inferred from a path)."""

    exposed: bool
    actions: Tuple[str, ...] = ()
    reason: Optional[str] = None


@dataclass(frozen=True)
class RouteResolution:
    """Explicit, deterministic route-resolution strategy."""

    strategy: str  # "fail_on_multiple_match" | "first_priority"


@dataclass(frozen=True)
class Lifeline:
    ref: str


@dataclass(frozen=True)
class Payload:
    contract: Optional[str] = None
    no_payload_reason: Optional[str] = None


@dataclass(frozen=True)
class Message:
    id: str
    kind: str  # "boundary" | "self" | "control"
    sender: str  # YAML key: from
    recipient: str  # YAML key: to
    intent: str
    payload: Payload
    feature_refs: Tuple[str, ...] = ()
    wmbt_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Guard:
    id: str
    expression: str
    wmbt_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Fragment:
    id: str
    kind: str  # "alt" | "opt"
    guards: Tuple[Guard, ...]
    acceptance_refs: Tuple[str, ...] = ()
    wmbt_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Invariant:
    id: str
    expression: str
    wmbt_ref: Optional[str] = None


@dataclass(frozen=True)
class Residual:
    id: str
    kind: str
    reason: str
    acceptance_ref: Optional[str] = None
    validator_ref: Optional[str] = None
    wmbt_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CategoryAssessment:
    """A typed not-applicable for one route category (issue #1554).

    Declared only for ``alternate``/``error``/``exception`` — ``nominal`` always
    requires routes. ``basis`` is a closed vocabulary, never prose: a free-text
    reason is an escape hatch that erodes as it gets copy-pasted. A
    ``discharged-by-residual`` basis names a declared residual, which must itself
    carry a reason, an acceptance_ref and a validator_ref, so discharging a
    category costs a bound obligation rather than a sentence.
    """

    category: str
    basis: str
    residual_ref: Optional[str] = None
    retires_with: Optional[int] = None


@dataclass(frozen=True)
class Projection:
    expected_sequence_digest: str
    fields: Tuple[str, ...] = ("step", "intent", "from", "to", "artifact")


@dataclass(frozen=True)
class Route:
    """One guarded route selecting exactly one target train.

    ``category`` is the route's declared variant classification. It is judged by
    comparing it against the ``category`` FIELD of the target train (issue #1421)
    — never by parsing the identity, which carries no classification digit.
    """

    route_id: str
    category: str
    priority: int
    guard_ref: str
    train_id: str
    train_path: str
    projection: Projection


@dataclass(frozen=True)
class Source:
    path: str
    content_digest: str


@dataclass(frozen=True)
class TrainStep:
    """One linear step of a target train, mirroring the train.schema step shape.

    ``sender``/``recipient`` carry the train YAML ``from``/``to`` keys (which are
    reserved words in Python). ``as_projection`` renders the step over an ordered
    subset of the projection fields for deterministic digesting.
    """

    step: int
    intent: str
    sender: str
    recipient: str
    artifact: str

    def as_projection(self, fields: Tuple[str, ...]) -> "list[tuple[str, object]]":
        mapping = {
            "step": self.step,
            "intent": self.intent,
            "from": self.sender,
            "to": self.recipient,
            "artifact": self.artifact,
        }
        return [(f, mapping[f]) for f in fields]


@dataclass(frozen=True)
class TrainInterlocking:
    """A fully parsed interlocking artifact plus the on-disk context it loaded from."""

    schema_version: str
    interlocking_id: str
    title: str
    theme: str
    status: str
    source: Source
    entrypoint: Entrypoint
    route_resolution: RouteResolution
    lifelines: Tuple[Lifeline, ...]
    messages: Tuple[Message, ...]
    routes: Tuple[Route, ...]
    fragments: Tuple[Fragment, ...] = ()
    invariants: Tuple[Invariant, ...] = ()
    residuals: Tuple[Residual, ...] = ()
    category_assessments: Tuple[CategoryAssessment, ...] = ()
    # On-disk context (populated by load_interlocking; not part of digest content).
    loaded_from: Optional[Path] = None
    repo_root: Optional[Path] = None

    def assessment_index(self) -> "dict[str, CategoryAssessment]":
        """category -> its declared typed not-applicable (issue #1554)."""
        return {ca.category: ca for ca in self.category_assessments}

    def routes_by_category(self) -> "dict[str, list[str]]":
        """category -> the route_ids declaring it (empty categories are absent)."""
        index: dict[str, list[str]] = {}
        for route in self.routes:
            index.setdefault(route.category, []).append(route.route_id)
        return index

    def residual_ids(self) -> "set[str]":
        return {rsd.id for rsd in self.residuals}

    def guard_index(self) -> "dict[str, Guard]":
        index: dict[str, Guard] = {}
        for frag in self.fragments:
            for guard in frag.guards:
                index[guard.id] = guard
        return index

    def lifeline_refs(self) -> "set[str]":
        return {ll.ref for ll in self.lifelines}

    def obligation_index(self) -> "dict[str, set[str]]":
        """Map each referenced WMBT obligation to the surface kinds that carry it.

        The single resolver behind the surface-coverage question (#1546): it walks
        every surface kind that can name an obligation — message, guard, fragment,
        invariant, residual — and returns ``{wmbt_ref: {surface_kind, ...}}``.

        It reports only what the document *declares*; it does not enumerate the
        WMBT population and does not decide whether an obligation is adequately
        surfaced. That judgement belongs to the validator (#1547), which needs the
        surface kinds — not a bare set of refs — to name the kind in its evidence.

        The surface kind is load-bearing, not decorative. Residual-sourced refs
        are tagged ``residual:<kind>`` and are deliberately NOT merged into the
        flow-surface kinds (``message``/``self``/``guard``/``fragment``/
        ``invariant``), because per #1543 a structural residual discharges route
        completeness (O2) ONLY — never a SMOKE obligation (O1/O3). Collapsing
        this dict to ``set(index)`` throws that distinction away; any caller
        judging SMOKE coverage must filter on the kind rather than membership.
        """
        index: "dict[str, set[str]]" = {}

        def _add(ref: "str | None", kind: str) -> None:
            if ref:
                index.setdefault(ref, set()).add(kind)

        for msg in self.messages:
            for ref in msg.wmbt_refs:
                _add(ref, "self" if msg.kind == "self" else "message")
        for frag in self.fragments:
            for ref in frag.wmbt_refs:
                _add(ref, "fragment")
            for guard in frag.guards:
                for ref in guard.wmbt_refs:
                    _add(ref, "guard")
        for inv in self.invariants:
            _add(inv.wmbt_ref, "invariant")
        for rsd in self.residuals:
            for ref in rsd.wmbt_refs:
                _add(ref, f"residual:{rsd.kind}")
        return index

    def residual_wmbt_refs(self, kind: str = "structural") -> "set[str]":
        """WMBT obligations a residual of ``kind`` names for ROUTE COMPLETENESS only.

        Distinct from ``{rsd.id for rsd in residuals}``, which lives in the
        ``residual:`` namespace and can never equal a ``wmbt:`` ref.

        SCOPE — the #1543 binding rule. A structural residual discharges **O2
        only** (every modeled route/category has an acceptance at an appropriate
        phase). It NEVER discharges:

          O1  every registered train has a resolvable train-level SMOKE
          O3  every executable WMBT is SMOKE-covered, by train or WMBT ownership

        A residual is an admission that an obligation has *no honest flow
        representation*, so it is the weakest possible evidence — it asserts the
        route space is accounted for, never that anything was executed. It is
        therefore NOT SMOKE evidence and must not be counted as such.

        Concretely, this is the misuse this docstring exists to prevent::

            covered = surfaced | il.residual_wmbt_refs()   # WRONG for O1/O3

        That union silently lets a structural residual satisfy a SMOKE
        obligation. This method returns a bare set with no phase or evidence
        dimension and cannot distinguish the two on its own; keeping O2 separate
        from O1/O3 is the CALLER's responsibility. Use ``obligation_index()``
        when the distinction matters — it tags residual-sourced refs as
        ``residual:<kind>``, which the flow-surface kinds never collide with.
        """
        return {
            ref
            for rsd in self.residuals
            if rsd.kind == kind
            for ref in rsd.wmbt_refs
        }

    def route_by_id(self, route_id: str) -> Optional[Route]:
        for route in self.routes:
            if route.route_id == route_id:
                return route
        return None


__all__ = [
    "Entrypoint",
    "RouteResolution",
    "Lifeline",
    "Payload",
    "Message",
    "Guard",
    "Fragment",
    "Invariant",
    "Residual",
    "Projection",
    "Route",
    "Source",
    "TrainStep",
    "TrainInterlocking",
]
