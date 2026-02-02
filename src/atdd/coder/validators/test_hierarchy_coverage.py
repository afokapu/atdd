"""
Coder hierarchy coverage validation.

ATDD Hierarchy Coverage Spec v0.1 - Section 4: Coder Coverage Rules

Validates:
- Feature <-> Implementation (COVERAGE-CODE-4.1)
- Implementation <-> Tests (COVERAGE-CODE-4.2)

Architecture:
- Uses shared fixtures from atdd.coach.validators.shared_fixtures
- Phased rollout via atdd.coach.utils.coverage_phase
- Exception handling via .atdd/config.yaml coverage.exceptions
"""

import pytest
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.coverage_phase import (
    CoveragePhase,
    should_enforce,
    emit_coverage_warning
)


# Path constants
REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"
PYTHON_DIR = REPO_ROOT / "python"
SUPABASE_DIR = REPO_ROOT / "supabase"
WEB_DIR = REPO_ROOT / "web"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def find_python_implementations(wagon_slug: str, feature_slug: str) -> List[Path]:
    """
    Find Python implementation files for a feature.

    Searches for:
    - python/{wagon}/use_case_{feature}.py
    - python/{wagon}/service_{feature}.py
    - python/{wagon}/{feature}_handler.py
    - python/{wagon}/{feature}.py
    """
    implementations = []

    # Convert slugs to filesystem format
    wagon_dir = wagon_slug.replace("-", "_")
    feature_file = feature_slug.replace("-", "_")

    wagon_path = PYTHON_DIR / wagon_dir
    if not wagon_path.exists():
        return implementations

    # Check various patterns
    patterns = [
        f"use_case_{feature_file}.py",
        f"service_{feature_file}.py",
        f"{feature_file}_handler.py",
        f"{feature_file}.py",
    ]

    for pattern in patterns:
        impl_path = wagon_path / pattern
        if impl_path.exists():
            implementations.append(impl_path)

    # Also search subdirectories
    for subdir in wagon_path.iterdir():
        if subdir.is_dir() and not subdir.name.startswith("_"):
            for pattern in patterns:
                impl_path = subdir / pattern
                if impl_path.exists():
                    implementations.append(impl_path)

    return implementations


def find_typescript_implementations(wagon_slug: str, feature_slug: str) -> List[Path]:
    """
    Find TypeScript implementation files for a feature.

    Searches for:
    - supabase/functions/{wagon}/{feature}/index.ts
    - supabase/functions/{wagon}/{feature}/handler.ts
    - supabase/functions/{wagon}/{feature}.ts
    """
    implementations = []

    functions_dir = SUPABASE_DIR / "functions"
    if not functions_dir.exists():
        return implementations

    # Check various structures
    # Pattern 1: supabase/functions/{wagon}/{feature}/
    feature_dir = functions_dir / wagon_slug / feature_slug
    if feature_dir.exists():
        for pattern in ["index.ts", "handler.ts"]:
            impl_path = feature_dir / pattern
            if impl_path.exists():
                implementations.append(impl_path)

    # Pattern 2: supabase/functions/{wagon}/{feature}.ts
    wagon_dir = functions_dir / wagon_slug
    if wagon_dir.exists():
        feature_file = wagon_dir / f"{feature_slug}.ts"
        if feature_file.exists():
            implementations.append(feature_file)

    return implementations


def find_web_implementations(wagon_slug: str, feature_slug: str) -> List[Path]:
    """
    Find web/frontend implementation files for a feature.

    Searches for:
    - web/src/features/{wagon}/{feature}/
    - web/src/components/{feature}/
    """
    implementations = []

    # Pattern 1: web/src/features/{wagon}/{feature}/
    features_dir = WEB_DIR / "src" / "features" / wagon_slug / feature_slug
    if features_dir.exists():
        for pattern in ["index.tsx", "index.ts", f"{feature_slug}.tsx"]:
            impl_path = features_dir / pattern
            if impl_path.exists():
                implementations.append(impl_path)

    # Pattern 2: web/src/components/{feature}/
    components_dir = WEB_DIR / "src" / "components" / feature_slug
    if components_dir.exists():
        implementations.append(components_dir)

    return implementations


def has_implementation(wagon_slug: str, feature_slug: str) -> bool:
    """
    Check if a feature has any implementation.
    """
    python_impls = find_python_implementations(wagon_slug, feature_slug)
    ts_impls = find_typescript_implementations(wagon_slug, feature_slug)
    web_impls = find_web_implementations(wagon_slug, feature_slug)

    return len(python_impls) > 0 or len(ts_impls) > 0 or len(web_impls) > 0


def find_tests_for_implementation(impl_path: Path) -> List[Path]:
    """
    Find test files that might test an implementation.
    """
    tests = []

    if not impl_path.exists():
        return tests

    # For Python implementations
    if impl_path.suffix == ".py":
        impl_dir = impl_path.parent
        impl_name = impl_path.stem

        # Look for test_*.py in same directory
        for test_file in impl_dir.glob("test_*.py"):
            if impl_name in test_file.stem:
                tests.append(test_file)

        # Look for test file with matching name
        test_file = impl_dir / f"test_{impl_name}.py"
        if test_file.exists() and test_file not in tests:
            tests.append(test_file)

    # For TypeScript implementations
    elif impl_path.suffix == ".ts":
        impl_dir = impl_path.parent

        # Look for *.test.ts in same directory or test/ subdirectory
        for test_file in impl_dir.glob("*.test.ts"):
            tests.append(test_file)

        test_dir = impl_dir / "test"
        if test_dir.exists():
            for test_file in test_dir.glob("*.test.ts"):
                tests.append(test_file)

    return tests


# ============================================================================
# COVERAGE-CODE-4.1: Feature <-> Implementation Coverage
# ============================================================================


@pytest.mark.coder
def test_all_features_have_implementations(feature_files, coverage_exceptions):
    """
    COVERAGE-CODE-4.1: Every feature has implementation code.

    Given: Feature files in plan/*/features/
    When: Searching for corresponding implementation files
    Then: Every feature has at least one implementation in python/, supabase/, or web/
    """
    allowed_features = set(coverage_exceptions.get("features_without_implementation", []))
    violations = []

    for path, feature_data in feature_files:
        # Get wagon slug from path
        wagon_dir = path.parent.parent.name  # plan/{wagon}/features/{feature}.yaml
        wagon_slug = wagon_dir.replace("_", "-")

        # Get feature slug
        feature_slug = path.stem.replace("_", "-")
        feature_urn = feature_data.get("urn", f"feature:{wagon_slug}:{feature_slug}")

        # Skip draft features
        status = feature_data.get("status", "")
        if status == "draft":
            continue

        # Skip allowed exceptions
        if feature_urn in allowed_features or feature_slug in allowed_features:
            continue

        # Check for implementations
        if not has_implementation(wagon_slug, feature_slug):
            violations.append(
                f"{feature_urn}: no implementation found in python/, supabase/, or web/"
            )

    if violations:
        if should_enforce(CoveragePhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-CODE-4.1: Features without implementations:\n  " +
                "\n  ".join(violations[:20]) +
                (f"\n  ... and {len(violations) - 20} more" if len(violations) > 20 else "") +
                "\n\nImplement feature or add to coverage.exceptions.features_without_implementation"
            )
        else:
            for violation in violations[:10]:
                emit_coverage_warning(
                    "COVERAGE-CODE-4.1",
                    violation,
                    CoveragePhase.FULL_ENFORCEMENT
                )


# ============================================================================
# COVERAGE-CODE-4.2: Implementation <-> Tests Coverage
# ============================================================================


@pytest.mark.coder
def test_all_implementations_have_tests(feature_files):
    """
    COVERAGE-CODE-4.2: Every implementation has at least one test.

    Given: Feature implementations in python/, supabase/, web/
    When: Searching for corresponding test files
    Then: Every implementation has at least one test file
    """
    violations = []

    for path, feature_data in feature_files:
        # Get wagon and feature slugs
        wagon_dir = path.parent.parent.name
        wagon_slug = wagon_dir.replace("_", "-")
        feature_slug = path.stem.replace("_", "-")

        # Skip draft features
        status = feature_data.get("status", "")
        if status == "draft":
            continue

        # Find all implementations for this feature
        all_impls = (
            find_python_implementations(wagon_slug, feature_slug) +
            find_typescript_implementations(wagon_slug, feature_slug)
        )

        for impl_path in all_impls:
            tests = find_tests_for_implementation(impl_path)
            if not tests:
                violations.append(
                    f"{impl_path.relative_to(REPO_ROOT)}: no tests found"
                )

    if violations:
        if should_enforce(CoveragePhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-CODE-4.2: Implementations without tests:\n  " +
                "\n  ".join(violations[:20]) +
                (f"\n  ... and {len(violations) - 20} more" if len(violations) > 20 else "") +
                "\n\nAdd tests for the implementation"
            )
        else:
            for violation in violations[:10]:
                emit_coverage_warning(
                    "COVERAGE-CODE-4.2",
                    violation,
                    CoveragePhase.FULL_ENFORCEMENT
                )


# ============================================================================
# COVERAGE SUMMARY
# ============================================================================


@pytest.mark.coder
def test_coder_coverage_summary(feature_files):
    """
    COVERAGE-CODE-SUMMARY: Report coder coverage statistics.

    This test always passes but reports coverage metrics for visibility.
    """
    total_features = len(feature_files)
    features_with_impl = 0
    total_implementations = 0
    implementations_with_tests = 0

    for path, feature_data in feature_files:
        wagon_dir = path.parent.parent.name
        wagon_slug = wagon_dir.replace("_", "-")
        feature_slug = path.stem.replace("_", "-")

        # Count implementations
        python_impls = find_python_implementations(wagon_slug, feature_slug)
        ts_impls = find_typescript_implementations(wagon_slug, feature_slug)
        web_impls = find_web_implementations(wagon_slug, feature_slug)

        all_impls = python_impls + ts_impls + web_impls
        if all_impls:
            features_with_impl += 1
            total_implementations += len(all_impls)

            # Count implementations with tests
            for impl_path in python_impls + ts_impls:
                if find_tests_for_implementation(impl_path):
                    implementations_with_tests += 1

    # Calculate percentages
    feature_impl_pct = (features_with_impl / total_features * 100) if total_features > 0 else 0
    impl_test_pct = (implementations_with_tests / total_implementations * 100) if total_implementations > 0 else 0

    # Report summary
    summary = (
        f"\n\nCoder Coverage Summary:\n"
        f"  Features with implementations: {features_with_impl}/{total_features} ({feature_impl_pct:.1f}%)\n"
        f"  Total implementations: {total_implementations}\n"
        f"  Implementations with tests: {implementations_with_tests}/{total_implementations} ({impl_test_pct:.1f}%)"
    )

    # This test always passes - it's informational
    assert True, summary
