"""Station Master entrypoint — CLEAN bilateral-binding fixture.

The exposed interlocking's entrypoint.action (`resolve_match`) is wired into JOURNEY_MAP
as an interlocking route object whose path points at the real interlocking YAML, and the
interlocking_id matches the declaration. This closes station_to_declaration and
declaration_to_station.
"""
from trains.runtime import InterlockingRunner, TrainRunner

JOURNEY_MAP = {
    "start_match": "3001-solo-match-complete",
    "resolve_match": {
        # BINDING BREAK (station_to_declaration): interlocking_id is correct (so the interlocking
        # stays reachable for declaration_to_station) but path points at a YAML that does not exist.
        "interlocking_id": "interlocking:match-resolution",
        "path": "plan/_trains/_interlockings/does-not-exist.yaml",
    },
}


class StationMaster:
    def __init__(self):
        self.interlocking_runner = None
        self.train_runner = None

    def handle_action(self, action, inputs, state=None):
        mapping = JOURNEY_MAP[action]
        if isinstance(mapping, str):
            self.train_runner = TrainRunner(f"plan/_trains/{mapping}.yaml")
            return self.train_runner.execute(mapping, inputs)
        self.interlocking_runner = InterlockingRunner(mapping["path"])
        resolution = self.interlocking_runner.resolve_train(action, inputs, state)
        self.train_runner = TrainRunner(resolution.selected_train_id)
        return self.train_runner.execute(inputs={}, capture_trace=True)
