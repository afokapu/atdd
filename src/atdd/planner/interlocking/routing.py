# URN: component:plan:train-interlocking:Routing:backend:application
# Runtime: python
# Purpose: Deterministic, fail-closed route resolution over guard evaluation (#1248).
"""Route resolution for interlockings.

``evaluate_interlocking_route`` validates the requested action against the
declared entrypoint, evaluates each route's guard against the merged
inputs+state context, and resolves a single admissible ``route_id`` under the
declared strategy. It fails closed: ambiguity, no-match, an unknown action, or a
guard that cannot be parsed all raise rather than guessing.
"""
from __future__ import annotations

from typing import Any, List, Mapping, Optional

from .guards import GuardSyntaxError, evaluate_guard, parse_guard
from .models import Route, TrainInterlocking

__all__ = ["RouteResolutionError", "evaluate_interlocking_route", "matching_routes"]

FAIL_ON_MULTIPLE_MATCH = "fail_on_multiple_match"
FIRST_PRIORITY = "first_priority"


class RouteResolutionError(RuntimeError):
    """Raised when a route cannot be resolved deterministically (fail-closed)."""


def _context(inputs: Optional[Mapping[str, Any]], state: Optional[Mapping[str, Any]]) -> dict:
    ctx: dict = {}
    if state:
        ctx.update(state)
    if inputs:
        ctx.update(inputs)  # request/action inputs win over the state snapshot
    return ctx


def matching_routes(
    interlocking: TrainInterlocking,
    inputs: Optional[Mapping[str, Any]] = None,
    state: Optional[Mapping[str, Any]] = None,
) -> List[Route]:
    """Return every route whose guard evaluates true against the merged context."""
    ctx = _context(inputs, state)
    guards = interlocking.guard_index()
    matched: List[Route] = []
    for route in interlocking.routes:
        guard = guards.get(route.guard_ref)
        if guard is None:
            raise RouteResolutionError(
                f"route {route.route_id!r} references unknown guard {route.guard_ref!r}"
            )
        try:
            ast = parse_guard(guard.expression)
        except GuardSyntaxError as exc:
            raise RouteResolutionError(
                f"guard {guard.id!r} for route {route.route_id!r} is invalid: {exc}"
            ) from exc
        if evaluate_guard(ast, ctx):
            matched.append(route)
    return matched


def evaluate_interlocking_route(
    interlocking: TrainInterlocking,
    action: str,
    inputs: Optional[Mapping[str, Any]] = None,
    state: Optional[Mapping[str, Any]] = None,
) -> str:
    """Resolve a single ``route_id`` for ``action`` + ``inputs``/``state``.

    Fails closed (raises :class:`RouteResolutionError`) on an unexposed
    entrypoint, an unknown action, no matching route, ambiguous matches under
    ``fail_on_multiple_match``, or non-unique priorities under ``first_priority``.
    """
    ep = interlocking.entrypoint
    if not ep.exposed:
        raise RouteResolutionError(
            f"interlocking {interlocking.interlocking_id!r} is not exposed; "
            f"reason={ep.reason!r}"
        )
    if action not in ep.actions:
        raise RouteResolutionError(
            f"action {action!r} is not a declared entrypoint action "
            f"of {interlocking.interlocking_id!r} (declared: {list(ep.actions)})"
        )

    matched = matching_routes(interlocking, inputs, state)
    if not matched:
        raise RouteResolutionError(
            f"no admissible route for action {action!r} on "
            f"{interlocking.interlocking_id!r}"
        )

    strategy = interlocking.route_resolution.strategy
    if strategy == FAIL_ON_MULTIPLE_MATCH:
        if len(matched) > 1:
            ids = [r.route_id for r in matched]
            raise RouteResolutionError(
                f"multiple routes matched under fail_on_multiple_match: {ids}"
            )
        return matched[0].route_id

    if strategy == FIRST_PRIORITY:
        priorities = [r.priority for r in matched]
        if len(set(priorities)) != len(priorities):
            raise RouteResolutionError(
                f"first_priority requires unique priorities among matches; got {priorities}"
            )
        return min(matched, key=lambda r: r.priority).route_id

    raise RouteResolutionError(f"unknown route_resolution strategy {strategy!r}")
