"""atdd.journey — the executable journey engine (#1042 / #1034).

CORE: the platform-neutral journey grammar. ``TrainRunner.execute`` threads
``Cargo`` through a linear ``TrainSpec``, delegating each step to a wagon's
``run_train`` entry and validating the declared primary artifact. Divergence
(#1046), the durable event/replay model, declared dispatch (#1043), and the
behavior/delivery family + Acceptance Authority (#1083) layer on top of this
core without changing it. Distinct from the legacy issue-driven runner in
``atdd.train`` (that is being renamed ``IssueRunner`` by #1038).
"""
from .cargo import Cargo, CargoKeyError
from .runner import TrainRunner, RunTrain, WagonResolver
from .types import (
    Divergence,
    STATUS_DIVERGED,
    STATUS_FAILURE,
    STATUS_SUCCESS,
    TrainResult,
    TrainSpec,
    TrainStep,
)

__all__ = [
    "Cargo",
    "CargoKeyError",
    "TrainRunner",
    "RunTrain",
    "WagonResolver",
    "TrainSpec",
    "TrainStep",
    "TrainResult",
    "Divergence",
    "STATUS_SUCCESS",
    "STATUS_FAILURE",
    "STATUS_DIVERGED",
]
