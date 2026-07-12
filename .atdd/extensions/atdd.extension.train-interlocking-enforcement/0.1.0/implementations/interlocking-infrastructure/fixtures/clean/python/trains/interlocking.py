"""InterlockingRunner route-control layer — CLEAN fixture.

Resolves exactly one admissible train into a structured InterlockingResolution and delegates linear
execution to TrainRunner. It never imports a wagon, calls run_train, loops over train.sequence, or
touches Cargo (core afokapu/atdd#1251).
"""
from dataclasses import dataclass

from trains.runner import TrainRunner


@dataclass(frozen=True)
class InterlockingResolution:
    interlocking_id: str
    route_id: str
    train_id: str
    train_path: str
    category: str
    category_digit: str
    guard_id: str
    reason: str


class InterlockingRunner:
    def __init__(self, interlocking_yaml_path):
        self._path = interlocking_yaml_path

    def resolve_train(self, action, inputs, state=None):
        # Evaluate guards (omitted) and fail closed on no/multiple match. Returns structured metadata.
        return InterlockingResolution(
            interlocking_id="interlocking:match-resolution",
            route_id="nominal-all-voted",
            train_id="3001-solo-match-complete",
            train_path="plan/_trains/3001-solo-match-complete.yaml",
            category="nominal",
            category_digit="3",
            guard_id="all-voted",
            reason="all participants voted",
        )

    def execute(self, action, inputs, state=None, timing=None, capture_trace=True):
        resolution = self.resolve_train(action, inputs, state)
        return TrainRunner(resolution.train_path).execute(
            resolution.train_id, inputs, timing=timing, capture_trace=capture_trace
        )
