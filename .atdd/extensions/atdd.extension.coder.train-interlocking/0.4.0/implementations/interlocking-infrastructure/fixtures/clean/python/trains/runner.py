"""TrainRunner — CLEAN fixture.

The production linear train executor: the ONLY component that runs wagons and carries Cargo between
them. This is legitimate execution and is not flagged (the detector only scans InterlockingRunner-
defining modules for direct wagon execution).
"""
from match.wagon import run_match


class Cargo(dict):
    """Artifact data plane carried between wagons inside a selected train."""


class TrainRunner:
    def __init__(self, train_path):
        self._train_path = train_path

    def execute(self, train_id, inputs, timing=None, capture_trace=True):
        cargo = Cargo(inputs)
        train = _load_train(self._train_path)
        for step in train.sequence:
            cargo = run_train(step, cargo)
        return {"selected_train_id": train_id, "artifacts": dict(cargo)}


def run_train(step, cargo):
    if step == "match":
        return run_match(cargo)
    return cargo


def _load_train(path):
    class _T:
        sequence = ["match"]

    return _T()
