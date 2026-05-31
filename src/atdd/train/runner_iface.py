"""TrainRunner Protocol + PolicyHandle (docs/coach-decomposition.md §4.7, Child 8).

The ``TrainRunner`` is the stateful execution seam that sits above the Child 7
``PersistenceStore`` and the Child 6 ``AgentController``: it creates runs,
materializes evidence, records events, dispatches agents, waits, resumes, runs
waves, and calls the runtime/integration adapters (§3.1.1). Coach-core stays pure
policy; the runner is the layer the CLI drives an issue through.

``PolicyHandle`` is the frozen bundle the CLI constructs — Coach-core's entry
module plus the run's frozen ``Conventions`` snapshot — and hands to the runner so
every decision in the run is attributable to one policy (§5.2 ``policy_handle_id``).

Layer discipline (§3.3): ``atdd.train.*`` MAY import ``atdd.coach.core``,
``atdd.runtime.*``, ``atdd.integrations.*`` and stdlib; it MUST NOT import
``atdd.cli`` or ``atdd.observer``. This module imports only stdlib typing + the
Coach-core ``Conventions`` type + the sibling ``atdd.train.types`` value types.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Protocol, runtime_checkable

from atdd.coach.core.types import Conventions

# Supporting value types referenced by the protocol live in atdd.train.types
# (§4.7 physical-location note); re-exported here for protocol-readability.
from atdd.train.types import (
    RunId,
    RunState,
    RunStatus,
    RunSummary,
    TrainEvent,
    WaveResult,
)


@dataclass(frozen=True)
class PolicyHandle:
    """Bundles Coach-core entry points + frozen Conventions (§4.7).

    Constructed by the CLI. ``coach_module`` provides ``next_transition`` /
    ``evaluate_evidence`` / ``review_phase_output`` / ``merge_readiness`` /
    ``escalation_for`` (the §4.3 pure functions); ``conventions`` is the frozen
    snapshot every decision in the run is evaluated against.
    """

    coach_module: ModuleType
    conventions: Conventions


@runtime_checkable
class TrainRunner(Protocol):
    """The stateful per-issue / per-wave execution layer (§4.7).

    ``JsonlTrainRunner`` (``atdd.train.runners.jsonl``) is the first/default
    implementation. ``resume`` + ``run_wave`` are the Child-9 (#896) surface; the
    Child-8 runner reserves them with ``NotImplementedError``.
    """

    def start_issue(self, issue_number: int, *, policy: PolicyHandle) -> RunId: ...

    def resume(self, run_id: RunId) -> None: ...

    def run_wave(
        self, issue_numbers: list[int], *, concurrency: int = 1
    ) -> WaveResult: ...

    def handle_event(self, run_id: RunId, event: TrainEvent) -> None: ...

    def status(self, run_id: RunId) -> RunStatus: ...

    def cancel(self, run_id: RunId, *, reason: str) -> None: ...


__all__ = [
    "PolicyHandle",
    "TrainRunner",
    "RunId",
    "RunState",
    "RunStatus",
    "RunSummary",
    "TrainEvent",
    "WaveResult",
]
