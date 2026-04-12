"""
Train route smoke test coverage validator.

Validates that every train registered in plan/_trains.yaml has smoke test
coverage in e2e/{train_id}/.  Smoke test files must:
- Match naming convention: *_smoke* or *-smoke* in stem
- Contain no mock imports (real infrastructure assertions only)

This extends test_smoke_coverage.py to cover FE train routes — BE parity.
The existing validator checks coverage gaps among trains that already have
contract tests.  This validator ensures every *registered* train has at least
one smoke test, regardless of whether contract tests exist.

Uses ratchet baseline: existing gaps are baselined, new trains without smoke
tests fail as regressions.

Convention: src/atdd/tester/conventions/smoke.convention.yaml
Related:    src/atdd/tester/validators/test_smoke_coverage.py

Architecture:
- Entities: TrainRouteSmokeStatus, SmokeViolation
- Use Cases: TrainRouteSmokeAnalyzer (reuses PlanTrainDiscovery, SmokeScanner)
- Tests: Orchestration layer (pytest test functions)
"""

import pytest
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

from atdd.coach.utils.repo import find_repo_root
from atdd.tester.validators.test_smoke_coverage import (
    PlanTrainDiscovery,
    SmokeScanner,
    Violation,
)


REPO_ROOT = find_repo_root()
E2E_DIR = REPO_ROOT / "e2e"
TRAINS_FILE = REPO_ROOT / "plan" / "_trains.yaml"


# ============================================================================
# LAYER 1: ENTITIES
# ============================================================================


@dataclass
class TrainRouteSmokeStatus:
    """Smoke test coverage status for a single registered train route."""
    train_id: str
    e2e_dir: Path
    smoke_files: List[Path] = field(default_factory=list)
    violations: List[Violation] = field(default_factory=list)

    @property
    def has_smoke_tests(self) -> bool:
        return len(self.smoke_files) > 0

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0


# ============================================================================
# LAYER 2: USE CASES
# ============================================================================


class TrainRouteSmokeAnalyzer:
    """Analyze smoke test coverage for every registered train route."""

    def __init__(self, e2e_dir: Path, trains_file: Path):
        self.e2e_dir = e2e_dir
        self.plan_discovery = PlanTrainDiscovery(trains_file)
        self.scanner = SmokeScanner()

    def _find_smoke_files(self, train_dir: Path) -> List[Path]:
        """Find smoke test files in a train's e2e directory."""
        if not train_dir.is_dir():
            return []

        smoke_files = []
        # Python smoke tests
        for f in sorted(train_dir.rglob("test_*.py")):
            if "_smoke" in f.stem:
                smoke_files.append(f)
        # TypeScript smoke tests
        for f in sorted(train_dir.rglob("*.test.ts")):
            if "_smoke" in f.stem or "-smoke" in f.stem:
                smoke_files.append(f)
        for f in sorted(train_dir.rglob("*.spec.ts")):
            if "_smoke" in f.stem or "-smoke" in f.stem:
                smoke_files.append(f)

        return smoke_files

    def analyze(self) -> List[TrainRouteSmokeStatus]:
        """Return smoke coverage status for every registered train."""
        train_ids = self.plan_discovery.discover()
        statuses = []

        for tid in train_ids:
            train_e2e = self.e2e_dir / tid
            smoke_files = self._find_smoke_files(train_e2e)

            status = TrainRouteSmokeStatus(
                train_id=tid,
                e2e_dir=train_e2e,
                smoke_files=smoke_files,
            )

            # Scan existing smoke files for convention violations
            if smoke_files:
                status.violations = self.scanner.scan(smoke_files)

            statuses.append(status)

        return statuses


def scan_train_route_smoke_coverage(repo_root: Path):
    """Scan entrypoint for baseline registration.

    Returns (count, violations_list) tuple.
    """
    e2e_dir = repo_root / "e2e"
    trains_file = repo_root / "plan" / "_trains.yaml"
    analyzer = TrainRouteSmokeAnalyzer(e2e_dir, trains_file)
    statuses = analyzer.analyze()

    # Coverage gaps: registered trains with no smoke tests
    gap_violations = [
        f"{s.train_id}: no smoke tests in e2e/{s.train_id}/"
        for s in statuses
        if not s.has_smoke_tests
    ]

    # Mock violations: smoke files that import mocking libraries
    mock_violations = [
        f"{v.file.relative_to(repo_root)}: {v.detail}"
        for s in statuses
        for v in s.violations
        if v.rule == "no_mock_imports"
    ]

    all_violations = gap_violations + mock_violations
    return len(all_violations), all_violations


# ============================================================================
# LAYER 4: TESTS
# ============================================================================


@pytest.mark.tester
def test_train_route_smoke_coverage(ratchet_baseline):
    """Every registered train must have at least one smoke test file.

    Convention: smoke.convention.yaml > coverage > train_routes
    Path convention: e2e/{train_id}/*_smoke*.py | *_smoke*.test.ts | *-smoke*.test.ts
    Rationale: Smoke tests verify real infrastructure. Every train route
    needs smoke coverage to catch integration failures that contract tests miss.
    Severity: ERROR with ratchet — existing gaps baselined, new trains fail.
    """
    analyzer = TrainRouteSmokeAnalyzer(E2E_DIR, TRAINS_FILE)
    statuses = analyzer.analyze()

    if not statuses:
        pytest.skip("No trains registered in plan/_trains.yaml")

    violations = [
        f"{s.train_id}: no smoke tests in e2e/{s.train_id}/"
        for s in statuses
        if not s.has_smoke_tests
    ]

    if violations:
        print(
            f"\n  {len(violations)} train route(s) have no smoke tests:\n"
            + "".join(f"    - {v}\n" for v in violations)
            + "  See: src/atdd/tester/conventions/smoke.convention.yaml"
        )

    ratchet_baseline.assert_no_regression(
        validator_id="train_route_smoke_coverage",
        current_count=len(violations),
        violations=violations,
    )


@pytest.mark.tester
def test_train_route_smoke_no_mocks():
    """Smoke tests for train routes must not import mocking libraries.

    Convention: smoke.convention.yaml > forbidden_patterns > mock_imports
    Rationale: Smoke tests verify real infrastructure. Mocks defeat the purpose.
    """
    analyzer = TrainRouteSmokeAnalyzer(E2E_DIR, TRAINS_FILE)
    statuses = analyzer.analyze()

    mock_violations = [
        v
        for s in statuses
        for v in s.violations
        if v.rule == "no_mock_imports"
    ]

    if mock_violations:
        details = "\n".join(
            f"    {v.file.relative_to(REPO_ROOT)}: {v.detail}"
            for v in mock_violations
        )
        pytest.fail(
            f"{len(mock_violations)} train route smoke test(s) import mocking libraries:\n"
            f"{details}\n\n"
            "Smoke tests must use real infrastructure, not mocks.\n"
            "See: src/atdd/tester/conventions/smoke.convention.yaml"
        )
