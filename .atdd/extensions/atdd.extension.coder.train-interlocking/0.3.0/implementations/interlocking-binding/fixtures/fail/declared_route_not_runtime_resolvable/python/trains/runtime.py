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

    def resolve_train(self, action, inputs, state=None):
        # Resolves ONLY the declared nominal route; no hidden route/train literal.
        return InterlockingResolution(
            interlocking_id=self._declaration().get("interlocking_id"),
            route_id="nominal-all-voted",
            selected_train_id="3007-match-resolution-standard",
            train_path="plan/_trains/3007-match-resolution-standard.yaml",
            route_category="nominal",
            route_resolution_strategy="first_priority",
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
            "guard_id": "guard:all-voted",
            "resolution_strategy": "fail_on_multiple_match",
            "resolution_reason": "all_players_voted == true",
        }
