# URN: component:atdd-runtime:interlocking-runner:Package:backend:application
# Runtime: python
# Purpose: Runtime route-control layer for train interlockings (#1251 / parent #1246).
"""Runtime ``InterlockingRunner`` — the route-control role for train interlockings.

This is the runtime counterpart to the #1248 planner artifact. An interlocking is
executable ONLY as route selection + validation; real execution is delegated to
the production ``TrainRunner``:

    Station Master
      -> InterlockingRunner.resolve_train(action, inputs, state)  # exactly one train
      -> TrainRunner.execute(selected_train_id, ...)

Direct ``action -> train_id`` routing stays valid (``DirectTrainTarget``);
interlocking routing is additive (``InterlockingTarget``). The runner reuses the
#1248 safe guard/route API (no raw ``eval``), fails closed on no-match /
ambiguous-match / unsound interlocking / category mismatch / missing train file,
and returns a structured ``InterlockingResolution`` carrying the trace metadata.

Route-boundary transitions (implicit TrainResult-driven chaining) are explicitly
DEFERRED in this issue — see ``docs/atdd-interlocking-runtime-boundary.md``. The
forbidden boundaries (no wagon execution, no Cargo mutation, no next-step
selection, no TrainRunner bypass/duplication, no raw eval) are enforced by the
package's contract tests and, cross-repo, by atdd-extensions #25/#26/#27.

Public API:

    resolve_journey(journey_map, action) -> DirectTrainTarget | InterlockingTarget
    InterlockingRunner(path, train_executor=...).resolve_train(action, inputs, state)
    InterlockingRunner(path, train_executor=...).execute(action, inputs, ...)
"""
from __future__ import annotations

from .runner import (
    InterlockingResolution,
    InterlockingResolutionError,
    InterlockingRunner,
    TrainExecutor,
)
from .station_master import (
    DirectTrainTarget,
    InterlockingTarget,
    JourneyTarget,
    StationMasterError,
    resolve_journey,
)

__all__ = [
    # runner
    "InterlockingRunner",
    "InterlockingResolution",
    "InterlockingResolutionError",
    "TrainExecutor",
    # station master
    "resolve_journey",
    "DirectTrainTarget",
    "InterlockingTarget",
    "JourneyTarget",
    "StationMasterError",
]
