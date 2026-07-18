# URN: test:train:0206-decommission-orphan-detector:E2E-001-orphan-detector-decommissioned-route-projects
# Train: train:0206-decommission-orphan-detector
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: Train-level SMOKE for 0206-decommission-orphan-detector — the orphan-detector route: an implementation bound to a convention no node declares.
#          At this phase the enforcement behaviour is not yet implemented, so this
#          smoke asserts the train's CURRENT deliverable: its interlocking route
#          resolves and projects onto the authored linear train sequence with a
#          matching digest. It grows to assert the real enforcement verdict as the
#          wagons land.
"""Train-level SMOKE: the orphan-detector-decommissioned route of the enforce-extension-conventions
interlocking projects onto train 0206-decommission-orphan-detector's linear sequence.

Structural (not live_smoke): proves the authored train + interlocking are coherent
and route-resolvable — the precondition for every wagon's behavioural work.
"""
from __future__ import annotations

from pathlib import Path

from atdd.planner.interlocking.loader import load_interlocking
from atdd.planner.interlocking.projections import project_route_to_train_sequence
from atdd.planner.interlocking.digest import route_projection_digest

REPO_ROOT = Path(__file__).resolve().parents[2]
IL_PATH = REPO_ROOT / "plan/_trains/_interlockings/enforce-extension-conventions.yaml"
ROUTE_ID = "orphan-detector-decommissioned"
TRAIN_ID = "0206-decommission-orphan-detector"


def test_decommission_orphan_detector_route_projects_onto_train_sequence() -> None:
    il = load_interlocking(IL_PATH)
    route = il.route_by_id(ROUTE_ID)
    assert route is not None, f"route {ROUTE_ID!r} not found in interlocking"
    assert route.train_id == TRAIN_ID

    steps = project_route_to_train_sequence(il, ROUTE_ID)
    assert steps, f"route {ROUTE_ID!r} projects to an empty sequence"

    computed = route_projection_digest(steps, route.projection.fields)
    assert computed == route.projection.expected_sequence_digest, (
        "projected sequence digest drifted from the authored interlocking"
    )
