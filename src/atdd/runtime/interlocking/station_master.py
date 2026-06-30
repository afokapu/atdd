# URN: component:atdd-runtime:interlocking-runner:StationMaster:backend:application
# Runtime: python
# Purpose: Station Master JOURNEY_MAP resolution — direct train or interlocking (#1251).
"""Station Master journey resolution.

The Station Master maps an inbound ``action`` to one of two route shapes, both
declared in ``JOURNEY_MAP``:

* a direct ``train_id`` string (the existing, still-valid path), or
* an additive ``{interlocking_id, path}`` mapping that routes through an
  :class:`~atdd.runtime.interlocking.runner.InterlockingRunner`.

Resolution is fail-closed: an unknown action or a mapping that is neither a
train_id string nor a well-formed interlocking descriptor raises rather than
guessing. This module is route *dispatch* only — it never executes a train; the
caller hands the resolved target to ``TrainRunner`` (direct) or to
``InterlockingRunner`` (interlocking), which then delegates to ``TrainRunner``.
Stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Union

__all__ = [
    "StationMasterError",
    "DirectTrainTarget",
    "InterlockingTarget",
    "JourneyTarget",
    "resolve_journey",
]


class StationMasterError(RuntimeError):
    """Raised when an action cannot be resolved to a well-formed journey target."""


@dataclass(frozen=True)
class DirectTrainTarget:
    """``action -> train_id`` — execute the linear train directly via TrainRunner."""

    train_id: str


@dataclass(frozen=True)
class InterlockingTarget:
    """``action -> {interlocking_id, path}`` — route through an InterlockingRunner."""

    interlocking_id: str
    path: str


JourneyTarget = Union[DirectTrainTarget, InterlockingTarget]


def resolve_journey(journey_map: Mapping[str, object], action: str) -> JourneyTarget:
    """Resolve ``action`` against ``journey_map`` to a typed journey target.

    Fail-closed: an unknown action, or a mapping value that is neither a
    ``train_id`` string nor a ``{interlocking_id, path}`` descriptor, raises
    :class:`StationMasterError`.
    """
    if action not in journey_map:
        raise StationMasterError(
            f"action {action!r} is not declared in JOURNEY_MAP "
            f"(declared: {sorted(journey_map)})"
        )
    mapping = journey_map[action]
    if isinstance(mapping, str):
        return DirectTrainTarget(train_id=mapping)
    if isinstance(mapping, Mapping):
        interlocking_id = mapping.get("interlocking_id")
        path = mapping.get("path")
        if isinstance(interlocking_id, str) and isinstance(path, str):
            return InterlockingTarget(interlocking_id=interlocking_id, path=path)
    raise StationMasterError(
        f"action {action!r} maps to an unsupported journey shape {mapping!r}; "
        f"expected a train_id string or an {{interlocking_id, path}} mapping"
    )
