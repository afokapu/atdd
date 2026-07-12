"""Interlocking runtime (InterlockingRunner + TrainRunner) — CLEAN bilateral-binding fixture.

InterlockingRunner.resolve_train returns a structured InterlockingResolution whose route_id and
selected_train_id are EXACTLY the route declared in the interlocking YAML — so runtime_to_declaration
holds (the runtime resolves no hidden route). Core afokapu/atdd#1251.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class InterlockingResolution:
    interlocking_id: str
    route_id: str
    selected_train_id: str
    train_path: str
    route_category: str
    route_category_digit: str
    guard_id: str
    resolution_strategy: str
    resolution_reason: str


class InterlockingRunner:
    def __init__(self, interlocking_yaml_path):
        self._path = interlocking_yaml_path

    def resolve_train(self, action, inputs, state=None):
        # BINDING BREAK (runtime_to_declaration): resolves a route_id declared in NO interlocking
        # YAML — a hidden route the loaded route space never admits.
        return InterlockingResolution(
            interlocking_id="interlocking:match-resolution",
            route_id="ghost-route-not-declared",
            selected_train_id="3007-match-resolution-standard",
            train_path="plan/_trains/3007-match-resolution-standard.yaml",
            route_category="nominal",
            route_category_digit="0",
            guard_id="guard:all-voted",
            resolution_strategy="fail_on_multiple_match",
            resolution_reason="all_players_voted == true",
        )


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
            "route_category_digit": "0",
            "guard_id": "guard:all-voted",
            "resolution_strategy": "fail_on_multiple_match",
            "resolution_reason": "all_players_voted == true",
        }
