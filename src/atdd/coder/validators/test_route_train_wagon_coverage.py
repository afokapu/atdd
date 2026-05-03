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

Phase 2 (GREEN): the analyzer module
``src/atdd/coder/validators/route_train_wagon_analyzer.py`` carries the
parser + plan loaders; this file holds the orchestration tests and the
ratchet wiring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.validators._violation import Violation
from atdd.coder.validators.route_train_wagon_analyzer import (
    RULE_UNREGISTERED_TRAIN,
    RULE_UNREGISTERED_WAGON,
    RULE_DYNAMIC_TRAIN_ID,
    SEVERITY_ARCHITECTURAL,
    SEVERITY_ADVISORY,
    RouteTrainWagonAnalyzer,
    analyze_router_file,
    load_registered_trains,
    load_registered_wagons,
)


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent

FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "route_train_wagon"
)

ALL_RULE_IDS = (
    RULE_UNREGISTERED_TRAIN,
    RULE_UNREGISTERED_WAGON,
    RULE_DYNAMIC_TRAIN_ID,
)


# ---------------------------------------------------------------------------
# Production scan plumbing (mirrors test_route_train_compliance.py)
# ---------------------------------------------------------------------------
_DEFAULT_ROUTER_PATTERNS = [
    "web/src/**/router.ts",
    "web/src/**/router.tsx",
    "web/src/**/routes.ts",
    "web/src/**/routes.tsx",
    "web/src/**/*-routes.ts",
    "web/src/**/*-routes.tsx",
    "web/src/**/App.tsx",
]


def _load_route_train_wagon_config() -> Dict:
    """Load the ``route_train_wagon_coverage`` block from .atdd/config.yaml."""
    config = load_atdd_config(REPO_ROOT)
    return config.get("route_train_wagon_coverage", {}) or {}


def _load_allowlist(cfg: Dict) -> Dict[str, str]:
    """Build ``{path: migration}`` from allowlist entries."""
    out: Dict[str, str] = {}
    for entry in cfg.get("allowlist", []) or []:
        path = (entry.get("path") or "").strip()
        migration = (entry.get("migration") or "").strip()
        if path:
            out[path] = migration
    return out


def _find_router_files(repo_root: Path, router_patterns: List[str]) -> List[Path]:
    """Resolve glob patterns to router files, excluding fixture trees."""
    seen: Set[Path] = set()
    files: List[Path] = []
    for pattern in router_patterns:
        for match in repo_root.glob(pattern):
            if match.is_file() and match not in seen:
                seen.add(match)
                files.append(match)
    return sorted(p for p in files if "/fixtures/" not in str(p))


def scan_route_train_wagon_coverage(
    repo_root: Path,
) -> Tuple[int, List[Violation]]:
    """Aggregate Violations across all router files in *repo_root*.

    Used by the orchestration test (with ``REPO_ROOT``) and by SMOKE
    tests (with ``tmp_path`` roots).
    """
    cfg = _load_route_train_wagon_config()
    router_patterns = cfg.get("router_patterns") or _DEFAULT_ROUTER_PATTERNS
    allowlist = _load_allowlist(cfg)

    router_files = _find_router_files(repo_root, router_patterns)
    if not router_files:
        return 0, []

    analyzer = RouteTrainWagonAnalyzer(
        trains_file=repo_root / "plan" / "_trains.yaml",
        wagons_file=repo_root / "plan" / "_wagons.yaml",
    )

    violations: List[Violation] = []
    for f in router_files:
        try:
            rel = str(f.relative_to(repo_root))
        except ValueError:
            rel = str(f)
        if rel in allowlist:
            continue
        violations.extend(analyzer.analyze(f, repo_root))
    return len(violations), violations


# ---------------------------------------------------------------------------
# Helpers used by inline RED tests below
# ---------------------------------------------------------------------------
def _load_registered_trains_from_fixture(yaml_path: Path) -> Dict[str, List[str]]:
    """Re-export of the analyzer's loader, kept here for test readability."""
    return load_registered_trains(yaml_path)


# ===========================================================================
# Inline RED tests (Phase 1 of #333; now passing under Phase 2 analyzer)
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

    registered_trains = _load_registered_trains_from_fixture(yaml_fixture)
    registered_wagons = {"registered-wagon-y"}  # ghost-wagon-not-registered missing

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


# ===========================================================================
# Orchestration tests
# ===========================================================================

@pytest.mark.coder
def test_route_train_wagon_coverage():
    """SPEC-CODER-ROUTE-0005 ratchet: no new route → train → wagon gaps.

    Given: router files matching ``route_train_wagon_coverage.router_patterns``
           (defaults to ``_DEFAULT_ROUTER_PATTERNS`` when unset).
    When:  each router file is analyzed against ``plan/_trains.yaml`` +
           ``plan/_wagons.yaml``.
    Then:  total violation count does not exceed the ratchet baseline.
    """
    cfg = _load_route_train_wagon_config()
    router_patterns = cfg.get("router_patterns") or _DEFAULT_ROUTER_PATTERNS
    router_files = _find_router_files(REPO_ROOT, router_patterns)
    if not router_files:
        pytest.skip(
            "No router files match route_train_wagon_coverage.router_patterns; "
            "configure .atdd/config.yaml or add a web/src router to enable."
        )

    count, violations = scan_route_train_wagon_coverage(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id="route_train_wagon_coverage",
        violations=violations,
    )


@pytest.mark.coder
def test_route_train_wagon_allowlist_hygiene():
    """SPEC-CODER-ROUTE-0005 (allowlist hygiene): every entry needs a migration.

    Given: ``route_train_wagon_coverage.allowlist`` in ``.atdd/config.yaml``.
    When:  iterating entries.
    Then:  entries missing a non-empty ``migration:`` field fail.
    """
    cfg = _load_route_train_wagon_config()
    entries = cfg.get("allowlist") or []
    if not entries:
        pytest.skip("No route_train_wagon_coverage.allowlist entries")

    missing: List[str] = []
    for entry in entries:
        path = (entry.get("path") or "<missing path>").strip()
        migration = (entry.get("migration") or "").strip()
        if not migration:
            missing.append(path)

    if missing:
        pytest.fail(
            "Allowlist entries missing migration reference:\n"
            + "\n".join(f"  - {p}" for p in missing)
            + "\nFix: add `migration: \"owner/repo#NNN\"` to each entry."
        )
