"""
Smoke test coverage validator.

Validates that smoke tests follow the smoke.convention.yaml rules:
- Trains with contract-level journey tests have smoke test coverage
- Smoke tests do not import mocking libraries
- Smoke test headers include Phase: SMOKE and Smoke: true markers

Architecture:
- Entities: Domain models (TrainCoverage, SmokeTestFile, Violation)
- Use Cases: Business logic (TrainDiscovery, SmokeScanner, CoverageAnalyzer)
- Adapters: Infrastructure (ReportFormatter)
- Tests: Orchestration layer (pytest test functions)

Convention: src/atdd/tester/conventions/smoke.convention.yaml
"""

import pytest
import re
import yaml
from pathlib import Path
from typing import List, Set
from dataclasses import dataclass, field

from atdd.coach.utils.repo import find_repo_root


# Path constants
REPO_ROOT = find_repo_root()
E2E_DIR = REPO_ROOT / "e2e"
TRAINS_FILE = REPO_ROOT / "plan" / "_trains.yaml"


# ============================================================================
# LAYER 1: ENTITIES (Domain Models)
# ============================================================================


@dataclass
class SmokeTestFile:
    """A smoke test file discovered in the e2e directory."""
    path: Path
    train_id: str
    has_smoke_header: bool = False
    has_phase_smoke: bool = False
    mock_imports: List[str] = field(default_factory=list)


@dataclass
class TrainCoverage:
    """Coverage summary for a single train."""
    train_id: str
    train_dir: Path
    contract_tests: List[Path] = field(default_factory=list)
    smoke_tests: List[Path] = field(default_factory=list)

    @property
    def has_contract_tests(self) -> bool:
        return len(self.contract_tests) > 0

    @property
    def has_smoke_tests(self) -> bool:
        return len(self.smoke_tests) > 0

    @property
    def gap(self) -> bool:
        """True if train has contract tests but no smoke tests."""
        return self.has_contract_tests and not self.has_smoke_tests


@dataclass
class Violation:
    """A convention violation found in a smoke test file."""
    file: Path
    rule: str
    severity: str  # "error" or "warning"
    detail: str


# ============================================================================
# LAYER 2: USE CASES (Business Logic)
# ============================================================================


class TrainDiscovery:
    """Discover trains and classify their test files."""

    def __init__(self, e2e_dir: Path):
        self.e2e_dir = e2e_dir

    def discover(self) -> List[TrainCoverage]:
        """Scan e2e/ for train directories and classify test files."""
        if not self.e2e_dir.exists():
            return []

        trains = []
        for train_dir in sorted(self.e2e_dir.iterdir()):
            if not train_dir.is_dir():
                continue
            # Train dirs match pattern: {train_id} (e.g., 3007-matchmaking)
            train_id = train_dir.name
            coverage = TrainCoverage(train_id=train_id, train_dir=train_dir)

            for test_file in sorted(train_dir.rglob("test_*.py")):
                if "_smoke" in test_file.stem:
                    coverage.smoke_tests.append(test_file)
                else:
                    coverage.contract_tests.append(test_file)

            # Also check TypeScript test files
            for test_file in sorted(train_dir.rglob("*.test.ts")):
                if "_smoke" in test_file.stem or "-smoke" in test_file.stem:
                    coverage.smoke_tests.append(test_file)
                else:
                    coverage.contract_tests.append(test_file)

            if coverage.has_contract_tests or coverage.has_smoke_tests:
                trains.append(coverage)

        return trains


class PlanTrainDiscovery:
    """Discover trains defined in plan/_trains.yaml."""

    def __init__(self, trains_file: Path):
        self.trains_file = trains_file

    def discover(self) -> List[str]:
        """Return list of train IDs defined in the plan."""
        if not self.trains_file.exists():
            return []
        try:
            with open(self.trains_file) as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            return []

        train_ids = []
        for _theme_key, theme in (data.get("trains") or {}).items():
            for _journey_key, trains in (theme or {}).items():
                for train in (trains if isinstance(trains, list) else []):
                    tid = train.get("train_id")
                    if tid:
                        train_ids.append(tid)
        return train_ids


# Forbidden mock import patterns per smoke.convention.yaml
_PYTHON_MOCK_PATTERNS = [
    re.compile(r"from\s+unittest\.mock\s+import"),
    re.compile(r"from\s+unittest\s+import\s+mock"),
    re.compile(r"import\s+mock\b"),
    re.compile(r"@patch\("),
    re.compile(r"MagicMock\("),
]

_TYPESCRIPT_MOCK_PATTERNS = [
    re.compile(r"vi\.fn\("),
    re.compile(r"vi\.mock\("),
    re.compile(r"jest\.fn\("),
    re.compile(r"jest\.mock\("),
]

_SMOKE_HEADER_RE = re.compile(r"#\s*Smoke:\s*true", re.IGNORECASE)
_PHASE_SMOKE_RE = re.compile(r"#\s*Phase:\s*SMOKE", re.IGNORECASE)


class SmokeScanner:
    """Scan smoke test files for convention violations."""

    def scan(self, smoke_files: List[Path]) -> List[Violation]:
        """Check smoke test files for forbidden patterns and missing headers."""
        violations = []

        for path in smoke_files:
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            lines = content.splitlines()

            # Check for mock imports
            is_python = path.suffix == ".py"
            patterns = _PYTHON_MOCK_PATTERNS if is_python else _TYPESCRIPT_MOCK_PATTERNS

            for i, line in enumerate(lines, 1):
                for pattern in patterns:
                    if pattern.search(line):
                        violations.append(Violation(
                            file=path,
                            rule="no_mock_imports",
                            severity="error",
                            detail=f"Line {i}: forbidden mock import: {line.strip()}",
                        ))

            # Check for Smoke: true header
            if not _SMOKE_HEADER_RE.search(content):
                violations.append(Violation(
                    file=path,
                    rule="header_compliance",
                    severity="error",
                    detail="Missing 'Smoke: true' header marker",
                ))

            # Check for Phase: SMOKE header
            if not _PHASE_SMOKE_RE.search(content):
                violations.append(Violation(
                    file=path,
                    rule="header_compliance",
                    severity="error",
                    detail="Missing 'Phase: SMOKE' header marker",
                ))

        return violations


class CoverageAnalyzer:
    """Analyze smoke test coverage across trains."""

    def __init__(self, e2e_dir: Path):
        self.discovery = TrainDiscovery(e2e_dir)
        self.scanner = SmokeScanner()

    def analyze(self):
        """Run full analysis: coverage gaps + file violations."""
        trains = self.discovery.discover()
        gaps = [t for t in trains if t.gap]

        all_smoke_files = []
        for t in trains:
            all_smoke_files.extend(t.smoke_tests)

        violations = self.scanner.scan(all_smoke_files)
        errors = [v for v in violations if v.severity == "error"]

        return trains, gaps, violations, errors


# ============================================================================
# LAYER 3: ADAPTERS (Presentation)
# ============================================================================


class ReportFormatter:
    """Format smoke coverage analysis for human consumption."""

    @staticmethod
    def format_coverage(trains: List[TrainCoverage], gaps: List[TrainCoverage]) -> str:
        lines = ["\n=== Smoke Test Coverage ===\n"]
        for t in trains:
            status = "GAP" if t.gap else "OK"
            lines.append(
                f"  [{status}] {t.train_id}: "
                f"{len(t.contract_tests)} contract, {len(t.smoke_tests)} smoke"
            )
        if gaps:
            lines.append(f"\n  {len(gaps)} train(s) with contract tests but no smoke tests:")
            for g in gaps:
                lines.append(f"    - {g.train_id} ({len(g.contract_tests)} contract tests)")
        return "\n".join(lines)

    @staticmethod
    def format_violations(violations: List[Violation]) -> str:
        if not violations:
            return ""
        lines = ["\n=== Smoke Convention Violations ===\n"]
        for v in violations:
            lines.append(f"  [{v.severity.upper()}] {v.file.relative_to(REPO_ROOT)}: {v.detail}")
        return "\n".join(lines)


# ============================================================================
# LAYER 4: TESTS (Orchestration)
# ============================================================================


@pytest.mark.tester
def test_smoke_tests_have_no_mock_imports():
    """Smoke tests must not import mocking libraries.

    Convention: smoke.convention.yaml > forbidden_patterns > mock_imports
    Rationale: Smoke tests verify real infrastructure. Mocks defeat the purpose.
    """
    analyzer = CoverageAnalyzer(E2E_DIR)
    trains, _, violations, _ = analyzer.analyze()

    mock_violations = [v for v in violations if v.rule == "no_mock_imports"]

    if mock_violations:
        formatter = ReportFormatter()
        report = formatter.format_violations(mock_violations)
        pytest.fail(
            f"{len(mock_violations)} smoke test(s) import mocking libraries:\n{report}\n\n"
            "Smoke tests must use real infrastructure, not mocks.\n"
            "See: src/atdd/tester/conventions/smoke.convention.yaml"
        )


@pytest.mark.tester
def test_smoke_tests_have_correct_headers():
    """Smoke test files must include Phase: SMOKE and Smoke: true headers.

    Convention: smoke.convention.yaml > header > rules
    Rationale: Headers enable machine discovery and distinguish smoke from contract tests.
    """
    analyzer = CoverageAnalyzer(E2E_DIR)
    trains, _, violations, _ = analyzer.analyze()

    header_violations = [v for v in violations if v.rule == "header_compliance"]

    if header_violations:
        formatter = ReportFormatter()
        report = formatter.format_violations(header_violations)
        pytest.fail(
            f"{len(header_violations)} smoke test header violation(s):\n{report}\n\n"
            "Every smoke test must include:\n"
            "  # Phase: SMOKE\n"
            "  # Smoke: true\n"
            "See: src/atdd/tester/conventions/smoke.convention.yaml"
        )


@pytest.mark.tester
def test_smoke_coverage_gaps(ratchet_baseline):
    """Trains with contract-level journey tests must have smoke tests.

    Convention: smoke.convention.yaml > coverage > rule
    Rationale: Contract tests validate schema/sequencing but miss real infra bugs.
    Severity: ERROR with ratchet — fails on regression, auto-seeds baseline for
    existing gaps.

    Checks trains in e2e/ that have contract tests but no smoke tests.
    (Plan trains with no e2e directory are checked by test_train_e2e_existence.)
    """
    analyzer = CoverageAnalyzer(E2E_DIR)
    trains, gaps, _, _ = analyzer.analyze()

    if not trains:
        pytest.skip("No e2e/ directory or no trains with tests")

    violations = [
        f"{g.train_id}: {len(g.contract_tests)} contract test(s), 0 smoke tests"
        for g in gaps
    ]

    if violations:
        formatter = ReportFormatter()
        report = formatter.format_coverage(trains, gaps)
        print(report)

    ratchet_baseline.assert_no_regression(
        validator_id="smoke_coverage_gaps",
        current_count=len(violations),
        violations=violations,
    )
