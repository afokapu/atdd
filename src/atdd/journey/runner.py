"""TrainRunner: the mechanical journey executor (#1042 / #1034).

``execute`` loads a ``TrainSpec``, threads ``Cargo`` through the strictly-linear
sequence, delegates each step to a wagon's ``run_train(inputs, timing)`` entry,
validates that the declared ``primary`` artifact was produced, merges the result
into cargo, and reports a ``TrainResult``. It holds NO business logic and NO
routing state — wagons do the work; the Station Master (a separate role) owns
dispatch. Divergence (the three-way match against a declared dispatch registry)
is layered on by #1046; this core handles the nominal/failure path and carries
the ``diverged`` slots so that extension is non-breaking. Stdlib-only.

The wagon entry is resolved through an injected ``wagon_resolver`` so the engine
is testable without importing real wagons (and so wagons stay decoupled).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from .cargo import Cargo

_log = logging.getLogger(__name__)
from .types import (
    STATUS_FAILURE,
    STATUS_SUCCESS,
    TrainResult,
    TrainSpec,
    TrainStep,
)

# A wagon's run_train: (inputs, timing) -> {artifact_urn: data}
RunTrain = Callable[[Dict[str, Any], Dict[str, float]], Dict[str, Any]]
WagonResolver = Callable[[str], RunTrain]


class TrainRunner:
    def __init__(self, wagon_resolver: WagonResolver) -> None:
        self._resolve = wagon_resolver

    def execute(
        self,
        spec: TrainSpec,
        inputs: Optional[Dict[str, Any]] = None,
        timing: Optional[Dict[str, float]] = None,
    ) -> TrainResult:
        cargo = Cargo(inputs)
        trace: list = []
        timing = timing or {}

        for step in spec.steps:
            try:
                run_train = self._resolve(step.wagon)
            except Exception as exc:  # unresolved wagon is a spec/wiring failure
                _log.warning(
                    "train step failed: wagon could not be resolved",
                    extra={
                        "train_id": spec.train_id,
                        "step_index": step.index,
                        "wagon": step.wagon,
                        "error": str(exc),
                    },
                )
                return TrainResult(
                    STATUS_FAILURE, cargo.as_dict(), trace,
                    detail=f"step {step.index}: cannot resolve wagon {step.wagon!r}: {exc}",
                )

            produced = run_train(cargo.as_dict(), timing)
            if not isinstance(produced, dict):
                return TrainResult(
                    STATUS_FAILURE, cargo.as_dict(), trace,
                    detail=f"step {step.index} ({step.wagon}): run_train must return a dict, got {type(produced).__name__}",
                )

            # Nominal three-way (core slice): the wagon must produce its declared
            # primary. Producing a different primary is where #1046 routes the
            # dispatch-map / divergence; until then it is a loud failure.
            if step.primary not in produced:
                return TrainResult(
                    STATUS_FAILURE, cargo.as_dict(), trace,
                    detail=(
                        f"step {step.index} ({step.wagon}): declared primary "
                        f"{step.primary!r} not produced (got {sorted(produced)})"
                    ),
                )

            cargo.merge(produced)
            trace.append({
                "step": step.index,
                "wagon": step.wagon,
                "primary": step.primary,
                "produced": sorted(produced.keys()),
            })

        return TrainResult(STATUS_SUCCESS, cargo.as_dict(), trace)
