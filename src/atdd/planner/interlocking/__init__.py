# URN: component:plan:train-interlocking:Package:backend:application
# Runtime: python
# Purpose: Stable Python API for the train interlocking artifact (#1248 / #1246).
"""Train interlocking artifact: the train-domain route-control model.

The interlocking is authoritative for the guarded route space; each route maps to
exactly one numbered linear train variant (the runtime-executable path consumed by
``TrainRunner``). Mermaid/SVG/coverage outputs are derived projections, never
sources of truth.

Stable, shell-free Python API (callable from planner validators and runtime):

    load_interlocking(path) -> TrainInterlocking
    validate_interlocking(interlocking, root) -> list[Violation]
    evaluate_interlocking_route(interlocking, action, inputs, state=None) -> route_id
    project_route_to_train_sequence(interlocking, route_id) -> list[TrainStep]
    ensure_interlocking_projections(interlocking_id, root) -> Path

Plus supporting primitives: the guard grammar (parse_guard/evaluate_guard), digest
helpers (normalized_interlocking_digest/route_projection_digest), and the typed
model dataclasses.
"""
from __future__ import annotations

from .digest import (
    canonicalize,
    normalized_interlocking_digest,
    route_projection_digest,
)
from .guards import GuardSyntaxError, evaluate_guard, parse_guard
from .loader import (
    InterlockingError,
    load_interlocking,
    load_schema,
    parse_interlocking,
    schema_path,
    target_train_category,
)
from .models import (
    CategoryAssessment,
    Entrypoint,
    Fragment,
    Guard,
    Invariant,
    Lifeline,
    Message,
    Payload,
    Projection,
    Residual,
    Route,
    RouteResolution,
    Source,
    TrainInterlocking,
    TrainStep,
)
from .projections import (
    build_coverage,
    ensure_interlocking_projections,
    project_route_to_train_sequence,
    render_mermaid,
)
from .route_space import (
    CATEGORIES,
    category_assessment_violations,
    registered_trains,
    route_space_admission_violations,
    route_targets,
)
from .routing import RouteResolutionError, evaluate_interlocking_route, matching_routes
from .stamp import stamp_interlocking_digests
from .validate import validate_interlocking
from .violations import Violation

__all__ = [
    # primary API
    "load_interlocking",
    "validate_interlocking",
    "evaluate_interlocking_route",
    "project_route_to_train_sequence",
    "ensure_interlocking_projections",
    # guard grammar
    "parse_guard",
    "evaluate_guard",
    "GuardSyntaxError",
    # digests
    "normalized_interlocking_digest",
    "route_projection_digest",
    "canonicalize",
    "stamp_interlocking_digests",
    # route space (#1554)
    "CATEGORIES",
    "route_space_admission_violations",
    "category_assessment_violations",
    "registered_trains",
    "route_targets",
    # projections / routing helpers
    "build_coverage",
    "render_mermaid",
    "matching_routes",
    # errors
    "InterlockingError",
    "RouteResolutionError",
    # schema access
    "schema_path",
    "load_schema",
    "parse_interlocking",
    "target_train_category",
    # records + model
    "Violation",
    "TrainInterlocking",
    "TrainStep",
    "Entrypoint",
    "RouteResolution",
    "Lifeline",
    "Payload",
    "Message",
    "Guard",
    "Fragment",
    "Invariant",
    "Residual",
    "CategoryAssessment",
    "Projection",
    "Route",
    "Source",
]
