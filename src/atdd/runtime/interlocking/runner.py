# URN: component:atdd-runtime:interlocking-runner:InterlockingRunner:backend:application
# Runtime: python
# Purpose: Runtime route-control layer — resolve one train, delegate to TrainRunner (#1251).
"""Runtime ``InterlockingRunner`` — route control, never train execution.

An interlocking is executable *only* as route selection + validation. This runner
is the runtime role described in #1251 / parent #1246:

    Station Master
      -> InterlockingRunner.resolve_train(action, inputs, state)  # exactly one train
      -> TrainRunner.execute(selected_train_id, ...)              # real execution

``resolve_train`` reuses the #1248 artifact API (``load_interlocking`` +
``validate_interlocking`` + ``evaluate_interlocking_route``) so guards are
evaluated through the *declarative* grammar — there is no path to raw ``eval``.
It fails closed on no-match, ambiguous-match, an unsound interlocking, a selected
route whose category digit disagrees with its train_id, or a missing train file,
and returns a structured :class:`InterlockingResolution`.

``execute`` resolves a route and then delegates the selected train to the injected
production :class:`TrainExecutor` (the ``TrainRunner`` seam), handing it the
interlocking trace metadata so the runtime trace can carry route-control facts
alongside TrainRunner's step-level trace. This runner NEVER executes a wagon step,
picks the next step inside a train, or mutates Cargo — it has no such surface and
no access to one.

Layer note: ``atdd.runtime.interlocking`` imports the pure, IO-light
``atdd.planner.interlocking`` artifact API (value types + side-effect-free
functions) and stdlib only. It does not import ``atdd.coach`` / ``atdd.train`` /
``atdd.integrations``; the production train runner is supplied through the
``TrainExecutor`` Protocol so the route-control layer stays decoupled.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from atdd.planner.interlocking import (
    CATEGORY_BY_DIGIT,
    InterlockingError,
    RouteResolutionError,
    evaluate_interlocking_route,
    load_interlocking,
    validate_interlocking,
)
from atdd.planner.interlocking.models import Route, TrainInterlocking

from .station_master import (  # re-exported for callers of the route-control layer
    DirectTrainTarget,
    InterlockingTarget,
    StationMasterError,
    resolve_journey,
)

logger = logging.getLogger(__name__)

__all__ = [
    "InterlockingResolution",
    "InterlockingResolutionError",
    "InterlockingRunner",
    "TrainExecutor",
    # re-exported Station Master surface
    "DirectTrainTarget",
    "InterlockingTarget",
    "StationMasterError",
    "resolve_journey",
]


class InterlockingResolutionError(RuntimeError):
    """Raised when a route cannot be resolved/validated (fail-closed route control)."""


@dataclass(frozen=True)
class InterlockingResolution:
    """The single admissible route/train selection produced by ``resolve_train``.

    Structured metadata (not a bare ``train_id`` string) so the Station Master,
    the runtime trace, and the extension validators all bind to the same fields.
    """

    interlocking_id: str
    route_id: str
    train_id: str
    train_path: str
    category: str
    category_digit: str
    guard_id: str
    resolution_strategy: str
    reason: str

    def as_trace(self) -> "dict[str, str]":
        """Render the route-control trace fields required by #1251.

        These are folded into the runtime trace alongside TrainRunner's
        step-level trace (TrainRunner remains responsible for steps).
        """
        return {
            "interlocking_id": self.interlocking_id,
            "route_id": self.route_id,
            "selected_train_id": self.train_id,
            "route_category": self.category,
            "route_category_digit": self.category_digit,
            "guard_id": self.guard_id,
            "resolution_strategy": self.resolution_strategy,
            "resolution_reason": self.reason,
        }


@runtime_checkable
class TrainExecutor(Protocol):
    """The production ``TrainRunner`` seam this route-control layer delegates to.

    Real train execution (the linear wagon sequence + Cargo transport + step-level
    trace) is owned by the consuming runtime's TrainRunner. The InterlockingRunner
    only selects a train and calls ``execute``; it passes ``interlocking_trace`` so
    the runner can fold route-control facts into its trace.
    """

    def execute(
        self,
        train_id: str,
        *,
        inputs: Mapping[str, Any],
        state: Optional[Mapping[str, Any]] = None,
        timing: Optional[Mapping[str, Any]] = None,
        capture_trace: bool = True,
        interlocking_trace: Optional[Mapping[str, str]] = None,
    ) -> Any: ...


class InterlockingRunner:
    """Route-control runner: resolve one train, then delegate to ``TrainRunner``.

    ``train_executor`` is optional for the resolution-only use (validators / planner
    Confirm load+resolve without executing). ``execute`` requires it.
    """

    def __init__(
        self,
        interlocking_yaml_path: "str | Path",
        *,
        train_executor: Optional[TrainExecutor] = None,
    ) -> None:
        self._path = Path(interlocking_yaml_path)
        self._train_executor = train_executor

    # -- resolution ------------------------------------------------------- #
    def resolve_train(
        self,
        action: str,
        inputs: Mapping[str, Any],
        state: Optional[Mapping[str, Any]] = None,
    ) -> InterlockingResolution:
        """Resolve exactly one admissible route/train or fail closed.

        Steps (all via the #1248 safe API): load + shape-validate the YAML,
        semantically validate the interlocking, evaluate guarded routes against
        ``inputs``/``state`` under the declared strategy, then re-assert the
        *selected* route's category digit and train-file existence.
        """
        interlocking = self._load_and_validate()

        try:
            route_id = evaluate_interlocking_route(interlocking, action, inputs, state)
        except RouteResolutionError as exc:
            # Fail closed: unknown action, no match, ambiguity, or a guard that the
            # declarative grammar refuses (e.g. an injection payload) all land here.
            raise InterlockingResolutionError(
                f"could not resolve a single route for action {action!r} on "
                f"{interlocking.interlocking_id!r}: {exc}"
            ) from exc

        route = interlocking.route_by_id(route_id)
        if route is None:  # defensive: evaluator returned an id we cannot resolve
            raise InterlockingResolutionError(
                f"resolved route {route_id!r} is not present in "
                f"{interlocking.interlocking_id!r}"
            )

        self._validate_selected_route(interlocking, route)

        return InterlockingResolution(
            interlocking_id=interlocking.interlocking_id,
            route_id=route.route_id,
            train_id=route.train_id,
            train_path=route.train_path,
            category=route.category,
            category_digit=route.category_digit,
            guard_id=route.guard_ref,
            resolution_strategy=interlocking.route_resolution.strategy,
            reason=(
                f"route {route.route_id!r} selected for action {action!r} via guard "
                f"{route.guard_ref!r} under strategy "
                f"{interlocking.route_resolution.strategy!r}"
            ),
        )

    # -- execution (delegates; never executes a wagon itself) ------------- #
    def execute(
        self,
        action: str,
        inputs: Mapping[str, Any],
        state: Optional[Mapping[str, Any]] = None,
        timing: Optional[Mapping[str, Any]] = None,
        capture_trace: bool = True,
    ) -> Any:
        """Resolve a route, then delegate the selected train to ``TrainRunner``.

        The interlocking trace metadata is handed to the executor so the runtime
        trace carries route-control facts. This method runs no wagon step and
        mutates no Cargo — it only calls ``train_executor.execute``.
        """
        if self._train_executor is None:
            raise InterlockingResolutionError(
                "execute() requires a production TrainRunner (train_executor); "
                "interlockings never execute trains themselves"
            )

        resolution = self.resolve_train(action, inputs, state)
        logger.debug(
            "interlocking route resolved; delegating to TrainRunner",
            extra={
                "interlocking_id": resolution.interlocking_id,
                "route_id": resolution.route_id,
                "selected_train_id": resolution.train_id,
            },
        )
        return self._train_executor.execute(
            resolution.train_id,
            inputs=inputs,
            state=state,
            timing=timing,
            capture_trace=capture_trace,
            interlocking_trace=resolution.as_trace(),
        )

    # -- internals -------------------------------------------------------- #
    def _load_and_validate(self) -> TrainInterlocking:
        try:
            interlocking = load_interlocking(self._path)
        except InterlockingError as exc:
            raise InterlockingResolutionError(
                f"interlocking {self._path} could not be loaded: {exc}"
            ) from exc

        root = interlocking.repo_root or self._path.parent
        violations = validate_interlocking(interlocking, root)
        if violations:
            detail = "; ".join(f"{v.rule_id} {v.detail}" for v in violations)
            raise InterlockingResolutionError(
                f"interlocking {interlocking.interlocking_id!r} is not sound: {detail}"
            )
        return interlocking

    def _validate_selected_route(
        self, interlocking: TrainInterlocking, route: Route
    ) -> None:
        """Re-assert the selected route's category digit + train file (fail-closed).

        ``validate_interlocking`` already checks the whole document; this is a
        defense-in-depth re-check scoped to the *selected* route so a single
        admissible train can never be executed against a mismatched category or a
        missing file even if document-level validation were ever bypassed.
        """
        train_digit = route.train_id[1] if len(route.train_id) >= 2 else ""
        if route.category_digit != train_digit:
            raise InterlockingResolutionError(
                f"selected route {route.route_id!r} category_digit "
                f"{route.category_digit!r} does not match train {route.train_id!r} "
                f"category digit {train_digit!r}"
            )

        expected_category = CATEGORY_BY_DIGIT.get(route.category_digit)
        if expected_category is not None and route.category != expected_category:
            raise InterlockingResolutionError(
                f"selected route {route.route_id!r} category {route.category!r} does "
                f"not match category_digit {route.category_digit!r} "
                f"(expected {expected_category!r})"
            )

        root = interlocking.repo_root or self._path.parent
        train_file = Path(root) / route.train_path
        if not train_file.exists():
            raise InterlockingResolutionError(
                f"selected route {route.route_id!r} references missing train file "
                f"{route.train_path}"
            )
