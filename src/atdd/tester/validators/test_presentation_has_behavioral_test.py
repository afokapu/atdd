"""
Behavioral Test Assertion Validator — issue #356.

A presentation-layer component MUST have at least one test declaring
`Assertion: behavioral` in its URN header. Tests with `Assertion: structural`
(or no declaration) inspect source code without executing the component;
they pass even when the rendered feature is blank or broken.

Past incident (idea-issue #318): 63/63 R283 tests passed while the match
page rendered blank because all assertions were structural and 8 features
had been removed during ratchet trim.

Mode: warn-only initially (per #356 Decision #1). Validators emit reports
of presentation features missing behavioral coverage but do not fail the
suite during the migration window. Promotion to hard-fail is a follow-on.

Convention: see src/atdd/tester/conventions/red.convention.yaml
                § assertion_classification.
"""

from __future__ import annotations

import os
import re
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import resolve_code_root, resolve_stack_container
from atdd.coach.utils.graph.resolver import TestResolver


REPO_ROOT = find_repo_root()

# Stack roots come from .atdd/config.yaml; an undeclared stack drops out of
# the scan instead of crashing it (coach.graph.implementation-root-resolution).
# e2e/ is core's own tree, not a stack, so it stays repo-anchored.
_WEB_CONTAINER = resolve_stack_container("web", REPO_ROOT)
TEST_SCAN_DIRS = [
    d
    for d in (
        resolve_code_root("python", REPO_ROOT),
        resolve_stack_container("supabase", REPO_ROOT),
        _WEB_CONTAINER / "tests" if _WEB_CONTAINER is not None else None,
        REPO_ROOT / "e2e",
    )
    if d is not None
]

_TEST_FILE_PATTERNS = [
    re.compile(r"^test_.*\.py$"),
    re.compile(r"^.*_test\.py$"),
    re.compile(r"^.*_test\.dart$"),
    re.compile(r"^.*\.test\.tsx?$"),
    re.compile(r"^.*\.spec\.ts$"),
]

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".dart_tool",
    "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
    ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
    "fixtures",
}

# Acceptance test URN: test:{wagon}:{feature}:{WMBT}-{HARNESS}-{NNN}[-{slug}]
_TEST_URN_RE = re.compile(
    r"^test:([a-z][a-z0-9-]*):([a-z][a-z0-9-]*):([A-Z]\d{3})-([A-Z0-9]+)-(\d{3})(?:-([a-z0-9-]+))?$"
)


def _component_key(test_urn: str) -> Optional[str]:
    """
    Extract a presentation-component grouping key from an acceptance test URN.

    Tests targeting the same component share `wagon:feature:WMBT`, so we group
    by that triple. Journey tests (test:train:...) are not presentation
    components and return None.
    """
    if not test_urn or test_urn.startswith("test:train:"):
        return None
    m = _TEST_URN_RE.match(test_urn)
    if not m:
        return None
    wagon, feature, wmbt = m.group(1), m.group(2), m.group(3)
    return f"{wagon}:{feature}:{wmbt}"


def _iter_test_files(scan_dirs: Iterable[Path]) -> Iterable[Path]:
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(scan_dir):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if any(p.match(fname) for p in _TEST_FILE_PATTERNS):
                    yield Path(dirpath) / fname


def find_presentation_components_missing_behavioral_tests(
    scan_dirs: Optional[Iterable[Path]] = None,
) -> Dict[str, List[Path]]:
    """
    Walk test files and return presentation components that have no test
    declaring `Assertion: behavioral`.

    Returns:
        dict mapping component key (`wagon:feature:WMBT`) to the list of
        presentation test files that target it (all of which were either
        structural or undeclared). Empty dict means full coverage.
    """
    dirs = list(scan_dirs) if scan_dirs is not None else TEST_SCAN_DIRS

    by_component: Dict[str, List[Path]] = defaultdict(list)
    behavioral_components: Set[str] = set()

    for test_file in _iter_test_files(dirs):
        try:
            content = test_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        header = TestResolver.parse_test_header(content)
        if header.get("layer") != "presentation":
            continue

        key = _component_key(header.get("test_urn") or "")
        if key is None:
            continue

        by_component[key].append(test_file)
        if header.get("assertion") == "behavioral":
            behavioral_components.add(key)

    missing: Dict[str, List[Path]] = {
        component: files
        for component, files in by_component.items()
        if component not in behavioral_components
    }
    return missing


# =============================================================================
# Self-tests for the helper logic (use inline fixtures, no real repo state).
# =============================================================================


def _write_test_file(path: Path, header_lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(header_lines) + "\n\ndef test_x():\n    pass\n"
    path.write_text(body, encoding="utf-8")


@pytest.mark.tester
def test_helper_flags_presentation_component_without_behavioral_test(tmp_path: Path):
    """A presentation component covered only by structural tests is flagged."""
    scan_dir = tmp_path / "python"
    _write_test_file(
        scan_dir / "wagon" / "feature" / "test" / "test_c001_unit_001_a.py",
        [
            "# URN: test:wagon-x:feature-y:C001-WIDGET-001-render",
            "# Acceptance: acc:wagon-x:C001-WIDGET-001-render",
            "# WMBT: wmbt:wagon-x:C001",
            "# Phase: RED",
            "# Layer: presentation",
            "# Assertion: structural",
        ],
    )

    missing = find_presentation_components_missing_behavioral_tests([scan_dir])

    assert "wagon-x:feature-y:C001" in missing
    assert len(missing["wagon-x:feature-y:C001"]) == 1


@pytest.mark.tester
def test_helper_passes_when_behavioral_test_exists(tmp_path: Path):
    """A component with at least one behavioral test is NOT flagged."""
    scan_dir = tmp_path / "python"
    _write_test_file(
        scan_dir / "wagon" / "feature" / "test" / "test_c001_unit_001_a.py",
        [
            "# URN: test:wagon-x:feature-y:C001-WIDGET-001-shape",
            "# Acceptance: acc:wagon-x:C001-WIDGET-001-shape",
            "# WMBT: wmbt:wagon-x:C001",
            "# Phase: RED",
            "# Layer: presentation",
            "# Assertion: structural",
        ],
    )
    _write_test_file(
        scan_dir / "wagon" / "feature" / "test" / "test_c001_unit_002_b.py",
        [
            "# URN: test:wagon-x:feature-y:C001-WIDGET-002-renders-score",
            "# Acceptance: acc:wagon-x:C001-WIDGET-002-renders-score",
            "# WMBT: wmbt:wagon-x:C001",
            "# Phase: GREEN",
            "# Layer: presentation",
            "# Assertion: behavioral",
        ],
    )

    missing = find_presentation_components_missing_behavioral_tests([scan_dir])

    assert missing == {}


@pytest.mark.tester
def test_helper_ignores_non_presentation_layers(tmp_path: Path):
    """Domain/application/integration/assembly tests are not in scope."""
    scan_dir = tmp_path / "python"
    for layer in ("domain", "application", "integration", "assembly"):
        _write_test_file(
            scan_dir / "wagon" / "feature" / "test" / f"test_c001_unit_001_{layer}.py",
            [
                f"# URN: test:wagon-x:feature-y:C001-UNIT-00{1 if layer == 'domain' else 2}-x",
                f"# Acceptance: acc:wagon-x:C001-UNIT-001-x",
                "# WMBT: wmbt:wagon-x:C001",
                "# Phase: RED",
                f"# Layer: {layer}",
                "# Assertion: structural",
            ],
        )

    missing = find_presentation_components_missing_behavioral_tests([scan_dir])

    assert missing == {}


@pytest.mark.tester
def test_helper_treats_undeclared_assertion_as_non_behavioral(tmp_path: Path):
    """
    Legacy tests without an Assertion: line are not behavioral by default —
    that's the migration entry point; they need at least one sibling test
    with `Assertion: behavioral` to clear the warning.
    """
    scan_dir = tmp_path / "python"
    _write_test_file(
        scan_dir / "wagon" / "feature" / "test" / "test_c001_unit_001_legacy.py",
        [
            "# URN: test:wagon-x:feature-y:C001-WIDGET-001-legacy",
            "# Acceptance: acc:wagon-x:C001-WIDGET-001-legacy",
            "# WMBT: wmbt:wagon-x:C001",
            "# Phase: GREEN",
            "# Layer: presentation",
            # no Assertion: line
        ],
    )

    missing = find_presentation_components_missing_behavioral_tests([scan_dir])

    assert "wagon-x:feature-y:C001" in missing


@pytest.mark.tester
def test_helper_handles_empty_scan_directory(tmp_path: Path):
    """No test files at all → empty result, no errors."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    missing = find_presentation_components_missing_behavioral_tests([empty_dir])

    assert missing == {}


# =============================================================================
# Repo-level audit. Warn-only per #356 Decision #1: emits warnings naming
# components missing behavioral coverage but never fails the suite.
# =============================================================================


@pytest.mark.tester
def test_repo_presentation_components_have_behavioral_coverage():
    """
    SPEC-TESTER-ASSERTION-0001: every presentation-layer component should
    have at least one test declaring `Assertion: behavioral`.

    Mode: warn-only during the migration window (#356 Decision #1).
    Promotion to hard-fail is a follow-on once the toolkit and downstream
    repos have migrated their presentation suites.
    """
    missing = find_presentation_components_missing_behavioral_tests()

    if not missing:
        # Nothing to report — either no presentation tests exist yet (toolkit
        # case) or all presentation components have behavioral coverage.
        return

    lines = [
        "Presentation components without `Assertion: behavioral` coverage "
        f"(warn-only — see #356):",
    ]
    for component, files in sorted(missing.items()):
        lines.append(f"  - {component}")
        for f in sorted(files):
            try:
                rel = f.relative_to(REPO_ROOT)
            except ValueError:
                rel = f
            lines.append(f"      structural-only test: {rel}")

    warnings.warn("\n".join(lines), stacklevel=2)
