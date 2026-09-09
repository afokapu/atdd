"""Station Master — DIRTY (direct wagon execution) fixture. Cleanly wired to runner + TrainRunner."""
from trains.interlocking import InterlockingRunner
from trains.runner import TrainRunner

JOURNEY_MAP = {
    "resolve_match": {
        "interlocking_id": "interlocking:match-resolution",
        "path": "plan/_trains/_interlockings/match-resolution.yaml",
    },
}


def dispatch(action, inputs, state=None):
    return InterlockingRunner(JOURNEY_MAP[action]["path"]).execute(action, inputs, state, TrainRunner)
