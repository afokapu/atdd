"""
Coder hierarchy coverage validation.

ATDD Hierarchy Coverage Spec v0.1 - Section 4: Coder Coverage Rules

Validates:
- Feature <-> Implementation (COVERAGE-CODE-4.1)
- Implementation <-> Tests (COVERAGE-CODE-4.2)

Architecture:
- Implementation roots are resolved from .atdd/config.yaml `code:` block via
  atdd.coach.utils.config.get_code_roots (see #327). Module-level path
  constants are intentionally NOT used — resolvers receive their root as
  an argument so new stacks can be added per-consumer without forking the
  validator.
- Uses shared fixtures from atdd.coach.validators.shared_fixtures
- Phased rollout via atdd.coach.utils.coverage_phase
- Exception handling via .atdd/config.yaml coverage.exceptions
"""

import logging
import pytest
from pathlib import Path
from typing import Callable, Dict, List, Optional

from atdd.coach.utils.config import get_code_roots, load_atdd_config
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.coverage_phase import (
    CoveragePhase,
    should_enforce,
    emit_coverage_warning
)
from atdd.coach.utils.manifest import is_manifest_slug


# Path constants — repo-derived only. Implementation-root constants
# (PYTHON_DIR/SUPABASE_DIR/WEB_DIR) are deliberately absent; resolvers
# take roots as arguments so consumers can declare their own layout.
REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"


# ============================================================================
# RESOLVER REGISTRY (stack-name → resolver callable)
# ============================================================================


def find_python_implementations(
    wagon_slug: str, feature_slug: str, python_root: Path
) -> List[Path]:
    """
    Find Python implementation files for a feature under ``python_root``.

    Searches for:
    - {python_root}/{wagon}/use_case_{feature}.py
    - {python_root}/{wagon}/service_{feature}.py
    - {python_root}/{wagon}/{feature}_handler.py
    - {python_root}/{wagon}/{feature}.py
    """
    implementations: List[Path] = []

    wagon_dir = wagon_slug.replace("-", "_")
    feature_file = feature_slug.replace("-", "_")

    wagon_path = python_root / wagon_dir
    if not wagon_path.exists():
        return implementations

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

    for subdir in wagon_path.iterdir():
        if subdir.is_dir() and not subdir.name.startswith("_"):
            for pattern in patterns:
                impl_path = subdir / pattern
                if impl_path.exists():
                    implementations.append(impl_path)

    return implementations


def find_typescript_implementations(
    wagon_slug: str, feature_slug: str, supabase_root: Path
) -> List[Path]:
    """
    Find TypeScript implementation files for a feature under ``supabase_root``.

    ``supabase_root`` is expected to point at ``supabase/functions`` (the
    default) or a consumer-overridden equivalent.
    """
    implementations: List[Path] = []

    if not supabase_root.exists():
        return implementations

    feature_dir = supabase_root / wagon_slug / feature_slug
    if feature_dir.exists():
        for pattern in ["index.ts", "handler.ts"]:
            impl_path = feature_dir / pattern
            if impl_path.exists():
                implementations.append(impl_path)

    wagon_dir = supabase_root / wagon_slug
    if wagon_dir.exists():
        feature_file = wagon_dir / f"{feature_slug}.ts"
        if feature_file.exists():
            implementations.append(feature_file)

    return implementations


def find_web_implementations(
    wagon_slug: str, feature_slug: str, web_root: Path
) -> List[Path]:
    """
    Find web/frontend implementation files for a feature under ``web_root``.

    ``web_root`` is expected to point at ``web/src`` (the default).
    """
    implementations: List[Path] = []

    features_dir = web_root / "features" / wagon_slug / feature_slug
    if features_dir.exists():
        for pattern in ["index.tsx", "index.ts", f"{feature_slug}.tsx"]:
            impl_path = features_dir / pattern
            if impl_path.exists():
                implementations.append(impl_path)

    components_dir = web_root / "components" / feature_slug
    if components_dir.exists():
        implementations.append(components_dir)

    return implementations


def find_toolkit_implementations(
    wagon_slug: str, feature_slug: str, toolkit_root: Path
) -> List[Path]:
    """
    Find toolkit implementation files for a feature under ``toolkit_root``.

    The toolkit layout (``src/atdd/{coach,planner,tester,coder}/...``) does
    not follow the consumer-repo ``{wagon}/{feature}.py`` shape — coach
    utilities are composed of several files per feature (e.g. custom-themes
    → theme_map.py + theme_scanner.py + custom_themes.py). Decision #5 uses
    fuzzy basename match: a file is a hit if the normalised feature slug
    (``config-driven-code-roots`` → ``config_driven_code_roots``) appears
    as a substring of the file stem, or if any hyphen-segment of the slug
    with ≥4 characters appears in the stem.
    """
    implementations: List[Path] = []

    if not toolkit_root.exists():
        return implementations

    norm_slug = feature_slug.replace("-", "_").lower()
    segments = [seg for seg in feature_slug.split("-") if len(seg) >= 4]

    for py_file in toolkit_root.rglob("*.py"):
        # Skip unit-test directories under the toolkit — those test the
        # toolkit itself and are not implementations of any feature. Note
        # that toolkit *validators* live at ``validators/test_*.py`` (no
        # nested ``tests/`` dir) and ARE implementations, so they must NOT
        # be skipped.
        if "/tests/" in py_file.as_posix():
            continue
        stem = py_file.stem.lower()
        if stem == "__init__":
            continue
        if norm_slug in stem:
            implementations.append(py_file)
            continue
        if any(seg in stem for seg in segments):
            implementations.append(py_file)

    return implementations


# Stack-name → resolver mapping. Adding a new stack means: add a
# find_{stack}_implementations function above and register it here.
_RESOLVERS: Dict[str, Callable[[str, str, Path], List[Path]]] = {
    "python": find_python_implementations,
    "supabase": find_typescript_implementations,
    "web": find_web_implementations,
    "toolkit": find_toolkit_implementations,
}


def _iter_resolvers(code_roots: Dict[str, Path]):
    """
    Yield (stack_name, resolver, absolute_root) for every code_roots entry
    whose stack has a registered resolver. Unknown stacks are skipped with
    a DEBUG log (Decision #2) — they must not crash the validator.
    """
    for stack, rel in code_roots.items():
        resolver = _RESOLVERS.get(stack)
        if resolver is None:
            logging.getLogger(__name__).debug("No resolver for stack %r; skipping", stack)
            continue
        abs_root = rel if rel.is_absolute() else (REPO_ROOT / rel)
        yield stack, resolver, abs_root


def has_implementation(
    wagon_slug: str,
    feature_slug: str,
    code_roots: Optional[Dict[str, Path]] = None,
) -> bool:
    """
    Check whether a feature has at least one implementation file under any
    registered stack resolver.

    The hyphen fallback (trying ``commit-state`` and then ``commit_state``)
    is preserved for backward compat with the consumer-repo layout.
    """
    if code_roots is None:
        code_roots = get_code_roots(load_atdd_config(REPO_ROOT))

    slug_variants = [(wagon_slug, feature_slug)]
    norm_wagon = wagon_slug.replace("-", "_")
    norm_feature = feature_slug.replace("-", "_")
    if (norm_wagon, norm_feature) != (wagon_slug, feature_slug):
        slug_variants.append((norm_wagon, norm_feature))

    for stack, resolver, abs_root in _iter_resolvers(code_roots):
        for w, f in slug_variants:
            if resolver(w, f, abs_root):
                return True
    return False


def _all_implementations(
    wagon_slug: str,
    feature_slug: str,
    code_roots: Dict[str, Path],
) -> List[Path]:
    """Collect every resolver's hits — used by the summary/coverage tests."""
    hits: List[Path] = []
    for stack, resolver, abs_root in _iter_resolvers(code_roots):
        hits.extend(resolver(wagon_slug, feature_slug, abs_root))
    return hits


def find_tests_for_implementation(impl_path: Path) -> List[Path]:
    """
    Find test files that might test an implementation.
    """
    tests: List[Path] = []

    if not impl_path.exists():
        return tests

    # For Python implementations
    if impl_path.suffix == ".py":
        impl_dir = impl_path.parent
        impl_name = impl_path.stem

        for test_file in impl_dir.glob("test_*.py"):
            if impl_name in test_file.stem:
                tests.append(test_file)

        test_file = impl_dir / f"test_{impl_name}.py"
        if test_file.exists() and test_file not in tests:
            tests.append(test_file)

    elif impl_path.suffix == ".ts":
        impl_dir = impl_path.parent

        for test_file in impl_dir.glob("*.test.ts"):
            tests.append(test_file)

        test_dir = impl_dir / "test"
        if test_dir.exists():
            for test_file in test_dir.glob("*.test.ts"):
                tests.append(test_file)

    return tests


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(scope="module")
def code_roots(atdd_config) -> Dict[str, Path]:
    """
    Resolve ``code:`` block from ``.atdd/config.yaml`` into an absolute-path
    stack-name → Path map. Plumbs through pytest so tests can override it
    with fixtures.
    """
    return get_code_roots(atdd_config)


# ============================================================================
# COVERAGE-CODE-4.1: Feature <-> Implementation Coverage
# ============================================================================


@pytest.mark.coder
def test_all_features_have_implementations(
    feature_files, coverage_exceptions, ratchet_baseline, code_roots
):
    """
    COVERAGE-CODE-4.1: Every feature has implementation code.

    Given: Feature files in plan/*/features/
    When:  Searching for corresponding implementation files across every
           stack declared in .atdd/config.yaml code: block
    Then:  Every feature has at least one implementation under one of the
           registered stack roots

    Uses ratchet baseline so planned-but-unimplemented features don't block CI.
    """
    allowed_features = set(coverage_exceptions.get("features_without_implementation", []))
    violations = []

    for path, feature_data in feature_files:
        wagon_dir = path.parent.parent.name
        wagon_slug = wagon_dir.replace("_", "-")
        feature_slug = path.stem.replace("_", "-")

        if is_manifest_slug(feature_slug):
            continue

        feature_urn = feature_data.get("urn", f"feature:{wagon_slug}:{feature_slug}")

        status = feature_data.get("status", "")
        if status == "draft":
            continue

        if feature_urn in allowed_features or feature_slug in allowed_features:
            continue

        if not has_implementation(wagon_slug, feature_slug, code_roots=code_roots):
            registered = ", ".join(sorted(code_roots))
            violations.append(
                f"{feature_urn}: no implementation found under any registered stack ({registered})"
            )

    ratchet_baseline.assert_no_regression(
        validator_id="hierarchy_coverage_features",
        current_count=len(violations),
        violations=violations,
    )


# ============================================================================
# COVERAGE-CODE-4.2: Implementation <-> Tests Coverage
# ============================================================================


@pytest.mark.coder
def test_all_implementations_have_tests(feature_files, code_roots):
    """
    COVERAGE-CODE-4.2: Every implementation has at least one test.

    Tests are only considered for implementations that produce test-shaped
    artifacts (Python .py and TypeScript .ts) — other resolvers (web
    components directory, toolkit multi-file) are reported by the summary
    but not subjected to 1:1 test-file requirements here.
    """
    violations = []

    for path, feature_data in feature_files:
        wagon_dir = path.parent.parent.name
        wagon_slug = wagon_dir.replace("_", "-")
        feature_slug = path.stem.replace("_", "-")

        status = feature_data.get("status", "")
        if status == "draft":
            continue

        python_root = code_roots.get("python")
        supabase_root = code_roots.get("supabase")
        all_impls: List[Path] = []
        if python_root is not None:
            abs_python = python_root if python_root.is_absolute() else REPO_ROOT / python_root
            all_impls += find_python_implementations(wagon_slug, feature_slug, abs_python)
        if supabase_root is not None:
            abs_supabase = supabase_root if supabase_root.is_absolute() else REPO_ROOT / supabase_root
            all_impls += find_typescript_implementations(wagon_slug, feature_slug, abs_supabase)

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
def test_coder_coverage_summary(feature_files, code_roots):
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

        all_impls = _all_implementations(wagon_slug, feature_slug, code_roots)
        if all_impls:
            features_with_impl += 1
            total_implementations += len(all_impls)

            for impl_path in all_impls:
                if impl_path.suffix not in {".py", ".ts"}:
                    continue
                if find_tests_for_implementation(impl_path):
                    implementations_with_tests += 1

    feature_impl_pct = (features_with_impl / total_features * 100) if total_features > 0 else 0
    impl_test_pct = (implementations_with_tests / total_implementations * 100) if total_implementations > 0 else 0

    summary = (
        f"\n\nCoder Coverage Summary:\n"
        f"  Stacks resolved: {', '.join(sorted(code_roots)) or '(none)'}\n"
        f"  Features with implementations: {features_with_impl}/{total_features} ({feature_impl_pct:.1f}%)\n"
        f"  Total implementations: {total_implementations}\n"
        f"  Implementations with tests: {implementations_with_tests}/{total_implementations} ({impl_test_pct:.1f}%)"
    )

    assert True, summary
