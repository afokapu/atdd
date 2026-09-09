"""Interlocking runtime (InterlockingRunner + TrainRunner) — CLEAN bilateral-binding fixture.

InterlockingRunner.resolve_train returns a structured InterlockingResolution whose route_id and
selected_train_id are EXACTLY the route declared in the interlocking YAML — so runtime_to_declaration
holds (the runtime resolves no hidden route). Core afokapu/atdd#1251.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class InterlockingResolution:
    interlocking_id: str
    route_id: str
    selected_train_id: str
    train_path: str
    route_category: str
    guard_id: str
    resolution_strategy: str
    resolution_reason: str


class InterlockingRunner:
    def __init__(self, interlocking_yaml_path):
        self._path = interlocking_yaml_path

    def _declaration(self):
        """READ the declaration this runner was handed.

        Without it the resolver transcribed the route space and
        coder.train.runtime-executes-the-declaration fired here too, so the fixture
        exhibited two defects instead of the one it exists to demonstrate.
        """
        return yaml.safe_load(Path(self._path).read_text(encoding="utf-8")) or {}

    def route_by_id(self, route_id):
        """The blessed route-space accessor.

        `runtime_to_declaration` traces a resolution kwarg back through a
        `route_by_id`-style accessor to the LOADED route space, which is how a
        data-driven runtime proves its resolution is not a hidden route. Selecting
        a route by filtering the list inline is equivalent at runtime but opaque to
        a provenance scan, and is reported undecidable.
        """
        for route in self._declaration().get("routes") or []:
            if route.get("route_id") == route_id:
                return _Route(self._declaration().get("interlocking_id"), route)
        raise KeyError(route_id)

    def resolve_train(self, action, inputs, state=None):
        admissible = [
            r.get("route_id")
            for r in (self._declaration().get("routes") or [])
            if self._guard_holds(r, inputs, state or {})
        ]
        if len(admissible) != 1:
            raise RuntimeError(
                f"fail_on_multiple_match: {len(admissible)} admissible routes for {action!r}"
            )
        route = self.route_by_id(admissible[0])
        return InterlockingResolution(
            interlocking_id=route.interlocking_id,
            route_id=route.route_id,
            selected_train_id=route.train_id,
            train_path=route.train_path,
            route_category=route.category,
            guard_id=route.guard_id,
            resolution_strategy="fail_on_multiple_match",
            resolution_reason=f"guard {route.guard_id!r} held",
        )

    @staticmethod
    def _guard_holds(route, inputs, state):
        if route.get("category") == "nominal":
            return bool(inputs.get("all_players_voted"))
        return bool(state.get(str(route.get("guard_id"))))



class _Route:
    """One declared route, read from the loaded route space."""

    def __init__(self, interlocking_id, data):
        self.interlocking_id = interlocking_id
        self.route_id = data.get("route_id")
        self.train_id = data.get("train_id")
        self.train_path = data.get("train_path")
        self.category = data.get("category")
        self.guard_id = data.get("guard_ref")




class TrainRunner:
    def __init__(self, train_id):
        self._train_id = train_id

    def execute(self, inputs=None, capture_trace=True):
        return _Result(self._train_id)


class _Result:
    """The trace REFLECTS the resolution it came from.

    Its fields were literals, which is a defect in its own right — the trace would
    publish the same route whatever was resolved — and it made every fixture in this
    tree transcribe the declared route space, so none of them proved only its own
    defect once executes-the-declaration started judging transcription.
    """

    def __init__(self, train_id, resolution=None):
        self.selected_train_id = train_id
        r = resolution
        self.trace = {
            "interlocking_id": getattr(r, "interlocking_id", None),
            "route_id": getattr(r, "route_id", None),
            "selected_train_id": train_id,
            "route_category": getattr(r, "route_category", None),
            "guard_id": getattr(r, "guard_id", None),
            "resolution_strategy": getattr(r, "resolution_strategy", None),
            "resolution_reason": getattr(r, "resolution_reason", None),
        }
