"""Station Master — DIRTY (station unlinked) fixture.

Declares an interlocking route but never references InterlockingRunner or TrainRunner — it handles the
route inline. Only coder.train.station-master-interlocking-routing should fire.
"""

JOURNEY_MAP = {
    "start_match": "3001-solo-match-complete",
    "resolve_match": {
        "interlocking_id": "interlocking:match-resolution",
        "path": "plan/_trains/_interlockings/match-resolution.yaml",
    },
}


def dispatch(action, inputs, state=None):
    return {"action": action, "mapping": JOURNEY_MAP[action]}
