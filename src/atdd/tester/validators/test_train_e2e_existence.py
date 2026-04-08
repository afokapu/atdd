"""
Train E2E existence validator.

Validates that every train registered in plan/_trains.yaml has at least one
E2E test file in e2e/{train_id}/.

Uses ratchet baseline for existing gaps so CI pipelines are not broken by
pre-existing missing coverage.  New trains that ship without E2E tests will
be caught as regressions.

Convention: src/atdd/tester/conventions/train.convention.yaml
Related:    src/atdd/tester/conventions/smoke.convention.yaml

Architecture:
- Entities: TrainE2EStatus
- Use Cases: E2EExistenceAnalyzer (reuses PlanTrainDiscovery from smoke coverage)
- Tests: Orchestration layer (pytest test function)
"""

import pytest
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

from atdd.coach.utils.repo import find_repo_root
from atdd.tester.validators.test_smoke_coverage import PlanTrainDiscovery


REPO_ROOT = find_repo_root()
E2E_DIR = REPO_ROOT / "e2e"
TRAINS_FILE = REPO_ROOT / "plan" / "_trains.yaml"


# ============================================================================
# LAYER 1: ENTITIES
# ============================================================================


@dataclass
class TrainE2EStatus:
    """E2E test existence status for a single train."""
    train_id: str
    e2e_dir: Path
    test_files: List[Path] = field(default_factory=list)

    @property
    def has_tests(self) -> bool:
        return len(self.test_files) > 0


# ============================================================================
# LAYER 2: USE CASES
# ============================================================================


class E2EExistenceAnalyzer:
    """Check that registered trains have E2E test directories with test files."""

    def __init__(self, e2e_dir: Path, trains_file: Path):
        self.e2e_dir = e2e_dir
        self.plan_discovery = PlanTrainDiscovery(trains_file)

    def analyze(self) -> List[TrainE2EStatus]:
        """Return status for every registered train."""
        train_ids = self.plan_discovery.discover()
        statuses = []

        for tid in train_ids:
            train_e2e = self.e2e_dir / tid
            status = TrainE2EStatus(train_id=tid, e2e_dir=train_e2e)

            if train_e2e.is_dir():
                # Collect Python and TypeScript test files
                status.test_files = sorted(
                    list(train_e2e.rglob("test_*.py"))
                    + list(train_e2e.rglob("*.test.ts"))
                    + list(train_e2e.rglob("*.spec.ts"))
                )

            statuses.append(status)

        return statuses


# ============================================================================
# LAYER 4: TESTS
# ============================================================================


@pytest.mark.tester
def test_train_e2e_existence(ratchet_baseline):
    """Every registered train must have at least one E2E test file.

    Convention: train.convention.yaml > e2e > existence
    Path convention: e2e/{train_id}/test_*.py | *.test.ts | *.spec.ts
    Rationale: Trains without E2E tests have no journey-level verification.
    The match state 401 bug demonstrated this failure mode.
    Severity: ERROR with ratchet.
    """
    analyzer = E2EExistenceAnalyzer(E2E_DIR, TRAINS_FILE)
    statuses = analyzer.analyze()

    if not statuses:
        pytest.skip("No trains registered in plan/_trains.yaml")

    violations = [
        f"{s.train_id}: no E2E tests in e2e/{s.train_id}/"
        for s in statuses
        if not s.has_tests
    ]

    if violations:
        print(
            f"\n  {len(violations)} train(s) have no E2E tests:\n"
            + "".join(f"    - {v}\n" for v in violations)
            + "  See: src/atdd/tester/conventions/train.convention.yaml"
        )

    ratchet_baseline.assert_no_regression(
        validator_id="train_e2e_existence",
        current_count=len(violations),
        violations=violations,
    )
