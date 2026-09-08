"""Interlocking runtime (InterlockingRunner + TrainRunner) — CLEAN bilateral-binding fixture.

The route space is LOADED, not transcribed. `resolve_train` reads the interlocking
YAML it was constructed with and selects a declared route from it, so the resolution
cannot drift from the declaration: delete the plan and this runtime stops answering,
which is the point.

This fixture used to hardcode the resolution — every field a literal, matching the
YAML by coincidence of authorship. It satisfied bilateral binding, because that rule
closes a TEXT-level correspondence. It could not satisfy
`coder.train.runtime-executes-the-declaration`, and rewriting it is what proves that
obligation is achievable rather than merely stated. Core afokapu/atdd#1251.
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
    def __init__(self, train_id):
        self.selected_train_id = train_id
        self.trace = {
            "interlocking_id": "interlocking:match-resolution",
            "route_id": "nominal-all-voted",
            "selected_train_id": train_id,
            "route_category": "nominal",
            "guard_id": "guard:all-voted",
            "resolution_strategy": "fail_on_multiple_match",
            "resolution_reason": "all_players_voted == true",
        }
