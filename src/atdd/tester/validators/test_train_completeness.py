"""
Train completeness chain validator.

Validates the full chain per train: train registered -> E2E exists -> smoke exists.
This is the validator equivalent of ``atdd inventory --trace`` but focused on
train-level completeness.

Uses ratchet baseline for existing gaps.

Convention: src/atdd/tester/conventions/train.convention.yaml
Related:    src/atdd/tester/conventions/smoke.convention.yaml
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
class TrainChainStatus:
    """Completeness status for a single train across the full chain."""
    train_id: str
    has_e2e: bool = False
    has_contract_tests: bool = False
    has_smoke_tests: bool = False
    e2e_count: int = 0
    contract_count: int = 0
    smoke_count: int = 0

    @property
    def complete(self) -> bool:
        """Train is complete if it has both E2E and smoke tests."""
        return self.has_e2e and self.has_smoke_tests

    @property
    def status_label(self) -> str:
        if self.complete:
            return "COMPLETE"
        if not self.has_e2e:
            return "NO_E2E"
        if self.has_contract_tests and not self.has_smoke_tests:
            return "NO_SMOKE"
        return "PARTIAL"


# ============================================================================
# LAYER 2: USE CASES
# ============================================================================


class CompletenessAnalyzer:
    """Analyze the full train -> E2E -> smoke chain for every registered train."""

    def __init__(self, e2e_dir: Path, trains_file: Path):
        self.e2e_dir = e2e_dir
        self.plan_discovery = PlanTrainDiscovery(trains_file)

    def analyze(self) -> List[TrainChainStatus]:
        """Return chain status for every registered train."""
        train_ids = self.plan_discovery.discover()
        results = []

        for tid in train_ids:
            status = TrainChainStatus(train_id=tid)
            train_dir = self.e2e_dir / tid

            if not train_dir.is_dir():
                results.append(status)
                continue

            status.has_e2e = True

            # Classify test files
            py_tests = list(train_dir.rglob("test_*.py"))
            ts_tests = list(train_dir.rglob("*.test.ts")) + list(
                train_dir.rglob("*.spec.ts")
            )
            all_tests = py_tests + ts_tests

            for test_file in all_tests:
                stem = test_file.stem
                if "_smoke" in stem or "-smoke" in stem:
                    status.smoke_count += 1
                else:
                    status.contract_count += 1

            status.e2e_count = len(all_tests)
            status.has_contract_tests = status.contract_count > 0
            status.has_smoke_tests = status.smoke_count > 0

            results.append(status)

        return results


# ============================================================================
# LAYER 3: ADAPTERS
# ============================================================================


class ChainReportFormatter:
    """Format completeness matrix for human consumption."""

    @staticmethod
    def format_matrix(statuses: List[TrainChainStatus]) -> str:
        header = (
            f"\n  {'Train':<40} {'E2E':>5} {'Contract':>10} {'Smoke':>7}  Status"
        )
        separator = "  " + "-" * 75
        lines = ["\n=== Train Completeness Chain ===", header, separator]

        for s in statuses:
            e2e = str(s.e2e_count) if s.has_e2e else "-"
            contract = str(s.contract_count) if s.has_contract_tests else "-"
            smoke = str(s.smoke_count) if s.has_smoke_tests else "-"
            lines.append(
                f"  {s.train_id:<40} {e2e:>5} {contract:>10} {smoke:>7}  {s.status_label}"
            )

        return "\n".join(lines)


# ============================================================================
# LAYER 4: TESTS
# ============================================================================


@pytest.mark.tester
def test_train_completeness(ratchet_baseline):
    """Every registered train must have the full chain: E2E + smoke.

    Convention: train.convention.yaml + smoke.convention.yaml
    Chain: train registered in _trains.yaml -> e2e/{train_id}/ exists
           -> smoke test (*_smoke.py) exists
    Rationale: Gaps in the chain are invisible when cross-referencing 3
    validator outputs manually.  This single validator surfaces them.
    Severity: ERROR with ratchet.
    """
    analyzer = CompletenessAnalyzer(E2E_DIR, TRAINS_FILE)
    statuses = analyzer.analyze()

    if not statuses:
        pytest.skip("No trains registered in plan/_trains.yaml")

    # A train is incomplete if it's missing any link in the chain
    incomplete = [s for s in statuses if not s.complete]

    violations = [
        f"{s.train_id}: {s.status_label} "
        f"(e2e={s.e2e_count}, contract={s.contract_count}, smoke={s.smoke_count})"
        for s in incomplete
    ]

    if violations:
        report = ChainReportFormatter.format_matrix(statuses)
        print(report)

    ratchet_baseline.assert_no_regression(
        validator_id="train_completeness",
        current_count=len(violations),
        violations=violations,
    )
