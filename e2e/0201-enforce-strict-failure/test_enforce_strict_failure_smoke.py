# URN: test:train:0201-enforce-strict-failure:E2E-001-strict-violation-fails-route-projects
# Train: train:0201-enforce-strict-failure
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: Train-level SMOKE for 0201-enforce-strict-failure — the strict-violation route: a strict node's FAIL exits the enforce job non-zero.
#          At this phase the enforcement behaviour is not yet implemented, so this
#          smoke asserts the train's CURRENT deliverable: its interlocking route
#          resolves and projects onto the authored linear train sequence with a
#          matching digest. It grows to assert the real enforcement verdict as the
#          wagons land.
"""Train-level SMOKE: the strict-violation-fails route of the enforce-extension-conventions
interlocking projects onto train 0201-enforce-strict-failure's linear sequence.

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
ROUTE_ID = "strict-violation-fails"
TRAIN_ID = "0201-enforce-strict-failure"


def test_enforce_strict_failure_route_projects_onto_train_sequence() -> None:
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
