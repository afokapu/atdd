"""InterlockingRunner — DIRTY (no resolve_train) fixture.

The class exists but exposes no resolve_train(...) entry point — there is no way to select an
admissible route before delegating (core afokapu/atdd#1251). It does delegate cleanly otherwise.
"""
from trains.runner import TrainRunner


class InterlockingRunner:
    def __init__(self, interlocking_yaml_path):
        self._path = interlocking_yaml_path

    def execute(self, action, inputs, state=None, _train_runner=TrainRunner):
        # BUG: jumps straight to a hardcoded train with no resolve_train route selection.
        return _train_runner("plan/_trains/3001-solo-match-complete.yaml").execute(
            "3001-solo-match-complete", inputs
        )
