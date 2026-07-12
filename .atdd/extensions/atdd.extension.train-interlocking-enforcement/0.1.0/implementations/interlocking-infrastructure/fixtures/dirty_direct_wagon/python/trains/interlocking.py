"""InterlockingRunner — DIRTY (direct wagon execution) fixture.

Runner + resolve_train + structured InterlockingResolution all present and the Station Master is
wired, but the runner executes wagons itself: it imports a wagon module, calls run_train(...), and
loops over train.sequence. No Cargo bleed. Only coder.train.interlocking-delegates-to-trainrunner
should fire.
"""
from dataclasses import dataclass

from match.wagon import run_match  # direct wagon import (forbidden)


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

    def execute(self, action, inputs, state=None, train_runner=None):
        train = _load_train(self.resolve_train(action, inputs, state).train_path)
        result = inputs
        for step in train.sequence:  # loops over train.sequence as executor (forbidden)
            result = run_train(step, result)  # calls run_train directly (forbidden)
        return run_match(result)


def run_train(step, data):
    return data


def _load_train(path):
    class _T:
        sequence = ["match"]

    return _T()
