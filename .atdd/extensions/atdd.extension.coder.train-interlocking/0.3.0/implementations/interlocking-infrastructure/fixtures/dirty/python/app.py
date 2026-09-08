"""Station Master entrypoint — DIRTY fixture.

Declares an interlocking route but NEVER references InterlockingRunner (unlinked) and NEVER references
TrainRunner (no delegation). Both are core afokapu/atdd#1251 violations.
"""

JOURNEY_MAP = {
    "start_match": "3001-solo-match-complete",
    "resolve_match": {
        "interlocking_id": "interlocking:match-resolution",
        "path": "plan/_trains/_interlockings/match-resolution.yaml",
    },
}


def dispatch(action, inputs, state=None):
    mapping = JOURNEY_MAP[action]
    # BUG: handles the interlocking route inline without routing through InterlockingRunner/TrainRunner.
    return {"action": action, "mapping": mapping}
