"""Station Master entrypoint — CLEAN fixture.

Routes both a direct train_id mapping and an interlocking route object, references the
InterlockingRunner route-control layer, and ultimately delegates execution to TrainRunner
(core afokapu/atdd#1251).
"""
from trains.interlocking import InterlockingRunner
from trains.runner import TrainRunner

JOURNEY_MAP = {
    "start_match": "3001-solo-match-complete",
    "resolve_match": {
        "interlocking_id": "interlocking:match-resolution",
        "path": "plan/_trains/_interlockings/match-resolution.yaml",
    },
}


def dispatch(action, inputs, state=None):
    mapping = JOURNEY_MAP[action]
    if isinstance(mapping, str):
        return TrainRunner(f"plan/_trains/{mapping}.yaml").execute(mapping, inputs)
    runner = InterlockingRunner(mapping["path"])
    return runner.execute(action, inputs, state)
