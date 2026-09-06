# URN: test:train:documentation-obligation:restore-obligation-observability:E2E-001-declaration-smoke
# Train: train:documentation-obligation:restore-obligation-observability
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Purpose: The error route of the documentation-obligation journey is declared, registered and
#          bilaterally bound to its interlocking, read through the real loaders over the real tree.
"""Smoke test for train:documentation-obligation:restore-obligation-observability.

This smokes the DECLARATION, not the journey. No gate runs a train journey in this
repository yet (#1734, #1598), so there is no runtime to drive end to end. What IS real
and executable today is that this route is registered, that its category matches the
train it selects, and that the binding is declared in both directions — which is exactly
what `interlocking-route-category-matches-train-id` and `interlocking-bilateral-binding`
enforce. When #1598 makes interlockings runtime-reachable, this file is where the journey
assertion belongs, and it must be rewritten rather than extended.

Route: COULD_NOT_CHECK -> restore-obligation-observability (error) — the capability ran but could not observe.
"""
from pathlib import Path

import yaml

from atdd.coach.utils.repo import find_repo_root

REPO_ROOT = find_repo_root()
TRAIN_ID = "train:documentation-obligation:restore-obligation-observability"
INTERLOCKING = REPO_ROOT / "plan/_trains/_interlockings/govern-documentation-obligation.yaml"
TRAIN_FILE = REPO_ROOT / "plan/_trains/documentation-obligation/restore-obligation-observability.yaml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_the_train_is_declared_on_disk() -> None:
    assert TRAIN_FILE.is_file(), f"{TRAIN_FILE} is not on disk"
    train = _load(TRAIN_FILE)
    assert train["train_id"] == TRAIN_ID
    assert train["category"] == "error"
    assert train["sequence"], "a declared train with no sequence routes nothing"


def test_the_interlocking_routes_to_it_with_a_matching_category() -> None:
    il = _load(INTERLOCKING)
    routes = [r for r in il["routes"] if r["train_id"] == TRAIN_ID]
    assert len(routes) == 1, f"expected exactly one route to {TRAIN_ID}, found {len(routes)}"
    route = routes[0]
    # planner.train.interlocking-route-category-matches-train-id
    assert route["category"] == _load(TRAIN_FILE)["category"]
    assert (REPO_ROOT / route["train_path"]).is_file()
    guards = {g["id"] for f in il.get("fragments", []) for g in f.get("guards", [])}
    assert route["guard_ref"] in guards, "route guard_ref resolves to no declared guard"


def test_the_binding_is_declared_in_both_directions() -> None:
    # planner.train.interlocking-bilateral-binding
    back = _load(TRAIN_FILE).get("source_interlocking") or {}
    assert back.get("interlocking_id") == _load(INTERLOCKING)["interlocking_id"]
    route = [r for r in _load(INTERLOCKING)["routes"] if r["train_id"] == TRAIN_ID][0]
    assert back.get("route_id") == route["route_id"]
