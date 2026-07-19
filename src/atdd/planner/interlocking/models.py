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
    # On-disk context (populated by load_interlocking; not part of digest content).
    loaded_from: Optional[Path] = None
    repo_root: Optional[Path] = None

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
        """WMBT obligations discharged by a residual of ``kind`` (default structural).

        Distinct from ``{rsd.id for rsd in residuals}``, which lives in the
        ``residual:`` namespace and can never equal a ``wmbt:`` ref.
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
