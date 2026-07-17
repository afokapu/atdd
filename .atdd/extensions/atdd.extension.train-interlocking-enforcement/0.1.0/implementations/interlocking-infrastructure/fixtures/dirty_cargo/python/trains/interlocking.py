"""InterlockingRunner — DIRTY (cargo bleed) fixture.

Runner + resolve_train + structured InterlockingResolution all present, Station Master wired, and NO
direct wagon execution. The defect is the Cargo boundary: the runner references/mutates Cargo and
stores an artifact_urn value (and a wagon imports interlocking, below). Only
coder.train.interlocking-does-not-carry-cargo should fire.
"""
from dataclasses import dataclass

from trains.runner import Cargo, TrainRunner


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

    def execute(self, action, inputs, state=None, train_runner=TrainRunner):
        resolution = self.resolve_train(action, inputs, state)
        cargo = Cargo(inputs)  # references the Cargo symbol (forbidden)
        cargo["artifact_urn:match"] = inputs  # mutates cargo + stores artifact_urn (forbidden)
        return train_runner(resolution.train_path).execute(resolution.train_id, cargo)
