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
        # BINDING BREAK (runtime_to_declaration): resolves a route_id declared in NO
        # interlocking YAML — a hidden route the loaded route space never admits.
        #
        # Its train is hidden too. The train id used to be a DECLARED one, which made this
        # fixture transcribe the declared route space as well, so it exhibited two defects
        # once executes-the-declaration started judging transcription. A hidden route has
        # no declared train, so naming one was wrong on its own terms.
        return InterlockingResolution(
            interlocking_id=self._declaration().get("interlocking_id"),
            route_id="ghost-route-not-declared",
            selected_train_id="9999-ghost-train-not-declared",
            train_path="plan/_trains/9999-ghost-train-not-declared.yaml",
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
    """The trace REFLECTS the resolution it came from.

    Its fields were literals, which is a defect in its own right — the trace would
    publish the same route whatever was resolved — and it made this fixture transcribe
    the declared route space on top of its own defect.
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
