"""InterlockingRunner — DIRTY (station unlinked) fixture.

A fully valid route-control layer (runner + resolve_train + structured InterlockingResolution +
TrainRunner delegation, no wagon execution / Cargo bleed). The ONLY defect lives in the Station
Master (app.py), so only coder.train.station-master-interlocking-routing should fire.
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

    def execute(self, action, inputs, state=None):
        resolution = self.resolve_train(action, inputs, state)
        return TrainRunner(resolution.train_path).execute(resolution.train_id, inputs)
