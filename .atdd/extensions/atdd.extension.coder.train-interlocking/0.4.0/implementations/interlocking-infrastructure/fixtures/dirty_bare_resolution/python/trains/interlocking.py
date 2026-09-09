"""InterlockingRunner — DIRTY (bare resolution) fixture.

Runner + resolve_train exist and the Station Master is wired, but resolve_train returns a bare
train_id string and NO structured InterlockingResolution model is defined. Only
coder.train.interlocking-resolution-model-exists should fire.
"""
from trains.runner import TrainRunner


class InterlockingRunner:
    def __init__(self, interlocking_yaml_path):
        self._path = interlocking_yaml_path

    def resolve_train(self, action, inputs, state=None):
        return "3001-solo-match-complete"  # bare train_id, no structured model

    def execute(self, action, inputs, state=None, train_runner=TrainRunner):
        train_id = self.resolve_train(action, inputs, state)
        return train_runner(f"plan/_trains/{train_id}.yaml").execute(train_id, inputs)
