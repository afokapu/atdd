"""Station Master — DIRTY (missing runner) fixture.

Declares an interlocking route but the consumer runtime ships NO InterlockingRunner class under
python/trains/ — the route-control layer does not exist (core afokapu/atdd#1251). It does reference
TrainRunner, so only the missing-runner defect is in play.
"""
from trains.runner import TrainRunner

JOURNEY_MAP = {
    "resolve_match": {
        "interlocking_id": "interlocking:match-resolution",
        "path": "plan/_trains/_interlockings/match-resolution.yaml",
    },
}


def dispatch(action, inputs, state=None):
    mapping = JOURNEY_MAP[action]
    return TrainRunner(mapping["path"]).execute(action, inputs)
