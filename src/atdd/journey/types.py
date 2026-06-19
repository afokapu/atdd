"""Core value types for the executable journey engine (#1042 / #1034).

A train is an executable journey: ``TrainRunner.execute`` threads a ``Cargo`` of
contract-validated artifacts through a strictly-linear sequence of steps, each
delegating to a wagon's ``run_train`` entry. These types are the mechanical
substrate; they hold no business logic. Stdlib-only by design (boundaries §3.3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class TrainStep:
    """One step of a train: a wagon produces its declared ``primary`` artifact.

    ``consumes``/``aux`` are declared IO (the per-step IO guard is enforced by
    #1044). The three-way divergence match (#1046) runs on ``primary`` only.
    """

    index: int
    wagon: str
    primary: str
    consumes: Tuple[str, ...] = ()
    aux: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TrainSpec:
    """A parsed train definition: a linear sequence of steps + optional family."""

    train_id: str
    steps: Tuple[TrainStep, ...]
    family: Optional[str] = None


# TrainResult.status values. Divergence/dispatch is wired by #1046; the engine
# core emits success/failure and carries the slots so later children extend it.
STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"
STATUS_DIVERGED = "diverged"


@dataclass
class Divergence:
    artifact_urn: str
    step_index: int


@dataclass
class TrainResult:
    """What a single ``execute`` produced. The runner reports; it does not route."""

    status: str
    cargo: Dict[str, Any]
    trace: List[Dict[str, Any]] = field(default_factory=list)
    divergence: Optional[Divergence] = None
    detail: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_SUCCESS
