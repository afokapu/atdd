"""Station Master — DIRTY (no resolve_train) fixture.

Properly wired to InterlockingRunner and TrainRunner, so the only defect is the runner's missing
resolve_train(...) entry point (core afokapu/atdd#1251).
"""
from trains.interlocking import InterlockingRunner
from trains.runner import TrainRunner

JOURNEY_MAP = {
    "resolve_match": {
        "interlocking_id": "interlocking:match-resolution",
        "path": "plan/_trains/_interlockings/match-resolution.yaml",
    },
}


def dispatch(action, inputs, state=None):
    mapping = JOURNEY_MAP[action]
    runner = InterlockingRunner(mapping["path"])
    return runner.execute(action, inputs, state, _train_runner=TrainRunner)
