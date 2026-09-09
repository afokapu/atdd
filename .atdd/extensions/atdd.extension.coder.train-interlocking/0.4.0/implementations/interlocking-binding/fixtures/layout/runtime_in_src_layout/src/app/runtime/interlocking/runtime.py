"""InterlockingRunner runtime living at a NON-default layout (src/, not python/trains/).

It resolves a route_id (``ghost-route-not-declared``) that appears in NO interlocking YAML — a hidden
route. The detector can only catch it once the resolved ``python_runtime`` layout actually points here
(via ATDD_INTERLOCKING_LAYOUT). Core afokapu/atdd#1251.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class InterlockingResolution:
    interlocking_id: str
    route_id: str
    selected_train_id: str


class InterlockingRunner:
    def __init__(self, interlocking_yaml_path):
        self._path = interlocking_yaml_path

    def resolve_train(self, action, inputs, state=None):
        # HIDDEN route: route_id resolves to a literal declared in no interlocking YAML.
        return InterlockingResolution(
            interlocking_id="interlocking:match-resolution",
            route_id="ghost-route-not-declared",
            selected_train_id="3007-match-resolution-standard",
        )
