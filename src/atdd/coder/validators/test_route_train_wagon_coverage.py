# URN: validator:govern-lifecycle:enforcement:RouteTrainWagonCoverage:backend:orchestration
# Runtime: python
# Purpose: Cross-check that every <TrainView trainId="..." /> in router files
#          resolves to a registered train, and that the resolved train's
#          wagons all exist in plan/_wagons.yaml.

"""
Route → Train → Wagon coverage validator.

Validates:
- BOUNDARIES-ROUTE-COVERAGE-001 (sev 3): trainId not in plan/_trains.yaml
- BOUNDARIES-ROUTE-COVERAGE-002 (sev 3): train.wagons references a wagon
  not in plan/_wagons.yaml
- BOUNDARIES-ROUTE-COVERAGE-003 (sev 1): trainId binds to a dynamic
  expression (prop, function call, ternary) that cannot be statically resolved

Spec ID: SPEC-CODER-ROUTE-0005 (human-readable string convention)
Closes the route → train → wagon segment of issue #318's three-way split.
Distinct from SPEC-CODER-PAGE-0004 (`test_route_train_compliance.py`) which
verifies that <TrainView> is *present*; this validator verifies the chain
*resolves* against the plan.

Convention: src/atdd/coder/conventions/frontend.convention.yaml
            (train_composition.enforcement.route_train_wagon_coverage)
Config:     .atdd/config.yaml → route_train_wagon_coverage
Baseline:   .atdd/baselines/coder.yaml → route_train_wagon_coverage

Phase 1 (RED): this file ships with stub `analyze_router_file` returning
[] so the four inline RED tests fail meaningfully. Phase 2 introduces
`route_train_wagon_analyzer.py` and replaces the stub with real
identifier-resolution + plan-lookup logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._violation import Violation


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent

FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "route_train_wagon"
)


# ---------------------------------------------------------------------------
# Rule constants (mirror frontend.convention.yaml::route_train_wagon_coverage)
# ---------------------------------------------------------------------------
RULE_UNREGISTERED_TRAIN = "BOUNDARIES-ROUTE-COVERAGE-001"
RULE_UNREGISTERED_WAGON = "BOUNDARIES-ROUTE-COVERAGE-002"
RULE_DYNAMIC_TRAIN_ID = "BOUNDARIES-ROUTE-COVERAGE-003"

SEVERITY_ARCHITECTURAL = 3  # rule-id.convention.yaml::severity_scale[3]
SEVERITY_ADVISORY = 1       # rule-id.convention.yaml::severity_scale[1]

ALL_RULE_IDS = (
    RULE_UNREGISTERED_TRAIN,
    RULE_UNREGISTERED_WAGON,
    RULE_DYNAMIC_TRAIN_ID,
)


# ---------------------------------------------------------------------------
# Public entrypoint (Phase 1 stub — replaced by Phase 2 analyzer delegation)
# ---------------------------------------------------------------------------
def analyze_router_file(
    router_path: Path,
    registered_trains: Dict[str, List[str]],
    registered_wagons: Set[str],
) -> List[Violation]:
    """Return Violations for route → train → wagon mismatches.

    Phase 1 stub: returns []. The three "fails" RED tests below assert
    specific Violations and therefore fail until Phase 2 wires up the
    real analyzer.
    """
    return []


# ---------------------------------------------------------------------------
# Helpers used by RED tests (kept small; real loaders live in Phase 2 module)
# ---------------------------------------------------------------------------
def _load_registered_trains(yaml_path: Path) -> Dict[str, List[str]]:
    """Parse a `_trains.yaml`-shaped doc into ``{train_id: [wagon, ...]}``.

    Mirrors the discovery pattern in
    `atdd.tester.validators.test_smoke_coverage.PlanTrainDiscovery` but
    keeps the per-train wagon list (which `PlanTrainDiscovery` discards).
    """
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    out: Dict[str, List[str]] = {}
    for theme in (data.get("trains") or {}).values():
        if not isinstance(theme, dict):
            continue
        for trains in theme.values():
            for train in trains or []:
                tid = train.get("train_id")
                if tid:
                    out[tid] = list(train.get("wagons") or [])
    return out


# ===========================================================================
# Inline RED tests
# ===========================================================================

@pytest.mark.coder
def test_unregistered_train_id_fails():
    """BOUNDARIES-ROUTE-COVERAGE-001: ghost trainId emits sev-3 Violation.

    Given: ghost_train.tsx with `<TrainView trainId="does-not-exist" />` and
           a `registered_trains` map that does NOT contain that id.
    When:  `analyze_router_file` runs.
    Then:  at least one Violation with rule_id=BOUNDARIES-ROUTE-COVERAGE-001
           and severity=3 is emitted.
    """
    fixture = FIXTURES_DIR / "ghost_train.tsx"
    assert fixture.exists(), f"missing fixture: {fixture}"

    registered_trains = {"registered-train-x": ["registered-wagon-y"]}
    registered_wagons = {"registered-wagon-y"}

    violations = analyze_router_file(fixture, registered_trains, registered_wagons)

    matches = [v for v in violations if v.rule_id == RULE_UNREGISTERED_TRAIN]
    assert matches, (
        f"expected at least one {RULE_UNREGISTERED_TRAIN} for "
        f"trainId=\"does-not-exist\"; got {violations!r}"
    )
    v = matches[0]
    assert v.severity == SEVERITY_ARCHITECTURAL, (
        f"{v.rule_id} severity={v.severity}, expected {SEVERITY_ARCHITECTURAL}"
    )
    assert "does-not-exist" in v.detail, (
        f"detail should name the offending trainId; got {v.detail!r}"
    )


@pytest.mark.coder
def test_unregistered_wagon_in_train_fails():
    """BOUNDARIES-ROUTE-COVERAGE-002: train referencing an unregistered wagon.

    Given: good_router.tsx with `<TrainView trainId="registered-train-x" />`
           and a `registered_trains` map (loaded from ghost_wagon.yaml) where
           that train lists an unregistered wagon.
    When:  `analyze_router_file` runs.
    Then:  at least one Violation with rule_id=BOUNDARIES-ROUTE-COVERAGE-002
           and severity=3 is emitted, naming the unregistered wagon.
    """
    fixture = FIXTURES_DIR / "good_router.tsx"
    yaml_fixture = FIXTURES_DIR / "ghost_wagon.yaml"
    assert fixture.exists(), f"missing fixture: {fixture}"
    assert yaml_fixture.exists(), f"missing fixture: {yaml_fixture}"

    registered_trains = _load_registered_trains(yaml_fixture)
    # Only registered-wagon-y is registered; ghost-wagon-not-registered isn't.
    registered_wagons = {"registered-wagon-y"}

    violations = analyze_router_file(fixture, registered_trains, registered_wagons)

    matches = [v for v in violations if v.rule_id == RULE_UNREGISTERED_WAGON]
    assert matches, (
        f"expected at least one {RULE_UNREGISTERED_WAGON} for "
        f"unregistered wagon; got {violations!r}"
    )
    v = matches[0]
    assert v.severity == SEVERITY_ARCHITECTURAL, (
        f"{v.rule_id} severity={v.severity}, expected {SEVERITY_ARCHITECTURAL}"
    )
    assert "ghost-wagon-not-registered" in v.detail, (
        f"detail should name the missing wagon; got {v.detail!r}"
    )


@pytest.mark.coder
def test_dynamic_train_id_warns():
    """BOUNDARIES-ROUTE-COVERAGE-003: unresolvable dynamic trainId warns (sev 1).

    Given: dynamic_unknown.tsx with `<TrainView trainId={props.trainId} />`.
    When:  `analyze_router_file` runs.
    Then:  exactly one Violation with rule_id=BOUNDARIES-ROUTE-COVERAGE-003
           and severity=1 is emitted; never a hard failure.
    """
    fixture = FIXTURES_DIR / "dynamic_unknown.tsx"
    assert fixture.exists(), f"missing fixture: {fixture}"

    registered_trains = {"registered-train-x": ["registered-wagon-y"]}
    registered_wagons = {"registered-wagon-y"}

    violations = analyze_router_file(fixture, registered_trains, registered_wagons)

    matches = [v for v in violations if v.rule_id == RULE_DYNAMIC_TRAIN_ID]
    assert matches, (
        f"expected at least one {RULE_DYNAMIC_TRAIN_ID} for dynamic trainId; "
        f"got {violations!r}"
    )
    v = matches[0]
    assert v.severity == SEVERITY_ADVISORY, (
        f"{v.rule_id} severity={v.severity}, expected {SEVERITY_ADVISORY} "
        f"(advisory — never hard-fail per Decision #4)"
    )
    # No hard-failure rule should be emitted for a dynamic prop pass-through.
    hard = [v for v in violations if v.rule_id != RULE_DYNAMIC_TRAIN_ID]
    assert not hard, (
        f"dynamic trainId must not emit hard-failure rules; got {hard!r}"
    )


@pytest.mark.coder
def test_resolved_chain_passes():
    """Negative: a fully-resolved chain emits zero Violations.

    Given: good_router.tsx with trainId="registered-train-x" and a
           `registered_trains` map where that train's wagons are all registered.
    When:  `analyze_router_file` runs.
    Then:  no Violations are emitted.
    """
    fixture = FIXTURES_DIR / "good_router.tsx"
    assert fixture.exists(), f"missing fixture: {fixture}"

    registered_trains = {"registered-train-x": ["registered-wagon-y"]}
    registered_wagons = {"registered-wagon-y"}

    violations = analyze_router_file(fixture, registered_trains, registered_wagons)

    assert violations == [], (
        f"expected zero violations for a fully-resolved chain; got {violations!r}"
    )
