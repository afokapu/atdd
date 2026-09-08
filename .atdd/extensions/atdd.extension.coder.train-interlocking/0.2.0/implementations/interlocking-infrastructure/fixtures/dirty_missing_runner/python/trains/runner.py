"""TrainRunner — DIRTY (missing runner) fixture.

The linear executor exists, but no InterlockingRunner route-control layer accompanies it.
"""


class TrainRunner:
    def __init__(self, train_path):
        self._train_path = train_path

    def execute(self, train_id, inputs, timing=None, capture_trace=True):
        return {"selected_train_id": train_id, "artifacts": {}}
