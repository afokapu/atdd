"""
Test commons structure consistency across Python and Frontend.

Validates both structural patterns:
- Python: Feature-first (complex features have internal layers, utilities are flat)
- Frontend: Layer-first (all code organized by architectural layer)

Both patterns enforce:
- Domain layer purity (no framework imports)
- Consistent naming (commons, not shared)
- Proper dependency direction

Convention: atdd/coder/conventions/commons.convention.yaml
"""

import pytest
import re
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_COMMONS = REPO_ROOT / "python" / "commons"
WEB_COMMONS = REPO_ROOT / "web" / "src" / "commons"
WEB_SRC = REPO_ROOT / "web" / "src"


# ============================================================================
# CROSS-STACK VALIDATION
# ============================================================================


@pytest.mark.coder
def test_commons_exists_in_both_stacks():
    """
    SPEC-CODER-COMMONS-0001: Commons exists in Python and Frontend.

    GIVEN: Project with polyglot codebase
    WHEN: Checking for commons directories
    THEN: Both python/commons and web/src/commons exist

    Validates: Consistent naming across stacks
    """
    missing = []

    if not PYTHON_COMMONS.exists():
        missing.append(f"python/commons/ (expected at {PYTHON_COMMONS})")

    if not WEB_COMMONS.exists():
        missing.append(f"web/src/commons/ (expected at {WEB_COMMONS})")

    if missing:
        pytest.fail(
            f"\n\nMissing commons directories:\n" +
            "\n".join(f"  - {m}" for m in missing)
        )


@pytest.mark.coder
def test_no_shared_directory_exists():
    """
    SPEC-CODER-COMMONS-0003: Old 'shared' directory should not exist.

    GIVEN: Project migrated to commons convention
    WHEN: Checking for legacy shared directory
    THEN: web/src/shared should not exist

    Validates: Migration from shared to commons complete
    """
    old_shared = REPO_ROOT / "web" / "src" / "shared"

    if old_shared.exists():
        files = list(old_shared.rglob("*"))
        pytest.fail(
            f"\n\nLegacy 'shared' directory still exists at web/src/shared\n"
            f"Contains {len(files)} files.\n"
            f"Migrate to web/src/commons/ and delete."
        )


# ============================================================================
# FRONTEND STRUCTURE VALIDATION (Layer-First)
# ============================================================================


@pytest.mark.coder
def test_frontend_commons_has_layer_structure():
    """
    SPEC-CODER-COMMONS-0002: Frontend commons has domain/application/integration layers.

    GIVEN: web/src/commons directory
    WHEN: Checking layer subdirectories
    THEN: domain/, application/, integration/ exist

    Validates: Layer-first structure for frontend
    """
    if not WEB_COMMONS.exists():
        pytest.skip("web/src/commons does not exist")

    expected_layers = ["domain", "application", "integration"]
    missing_layers = []

    for layer in expected_layers:
        layer_path = WEB_COMMONS / layer
        if not layer_path.exists():
            missing_layers.append(layer)

    if missing_layers:
        pytest.fail(
            f"\n\nMissing layers in web/src/commons/:\n" +
            "\n".join(f"  - {layer}/" for layer in missing_layers) +
            f"\n\nExpected structure (layer-first):\n" +
            "  web/src/commons/\n" +
            "  +-- domain/        # Framework-agnostic types\n" +
            "  +-- application/   # Hooks, context\n" +
            "  +-- integration/   # Clients, adapters"
        )


@pytest.mark.coder
def test_path_alias_uses_commons():
    """
    SPEC-CODER-COMMONS-0004: Path aliases use @commons, not @shared.

    GIVEN: tsconfig.json and vite.config.ts
    WHEN: Checking path aliases
    THEN: @commons is defined, @shared is not

    Validates: Correct path alias configuration
    """
    tsconfig_path = REPO_ROOT / "web" / "tsconfig.json"
    vite_config_path = REPO_ROOT / "web" / "vite.config.ts"

    issues = []

    if tsconfig_path.exists():
        content = tsconfig_path.read_text()
        if "@shared" in content:
            issues.append("tsconfig.json still contains @shared alias")
        if "@commons" not in content:
            issues.append("tsconfig.json missing @commons alias")

    if vite_config_path.exists():
        content = vite_config_path.read_text()
        if "'@shared'" in content or '"@shared"' in content:
            issues.append("vite.config.ts still contains @shared alias")
        if "'@commons'" not in content and '"@commons"' not in content:
            issues.append("vite.config.ts missing @commons alias")

    if issues:
        pytest.fail(
            "\n\nPath alias configuration issues:\n" +
            "\n".join(f"  - {i}" for i in issues)
        )


@pytest.mark.coder
def test_no_imports_from_shared():
    """
    SPEC-CODER-COMMONS-0005: No imports from @shared or ./shared.

    GIVEN: All TypeScript files in web/src
    WHEN: Checking import statements
    THEN: No imports reference @shared or relative shared paths

    Validates: All imports migrated to @commons
    """
    if not WEB_SRC.exists():
        pytest.skip("web/src does not exist")

    violations: List[str] = []

    for ts_file in WEB_SRC.rglob("*.ts"):
        _check_file_for_shared_imports(ts_file, violations)

    for tsx_file in WEB_SRC.rglob("*.tsx"):
        _check_file_for_shared_imports(tsx_file, violations)

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} files still importing from 'shared':\n\n" +
            "\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


def _check_file_for_shared_imports(file_path: Path, violations: List[str]) -> None:
    """Check a file for shared imports."""
    try:
        content = file_path.read_text()
    except Exception:
        return

    patterns = [
        r"from\s+['\"]@shared",
        r"from\s+['\"]\.\.?/shared",
        r"import\s+.*from\s+['\"]@shared",
        r"import\s+.*from\s+['\"]\.\.?/shared",
    ]

    for pattern in patterns:
        if re.search(pattern, content):
            rel_path = file_path.relative_to(REPO_ROOT)
            violations.append(f"  - {rel_path}")
            break


@pytest.mark.coder
def test_frontend_domain_no_framework_imports():
    """
    SPEC-CODER-COMMONS-0006: Frontend domain layer has no framework imports.

    GIVEN: Files in web/src/commons/domain/
    WHEN: Checking import statements
    THEN: No preact, react, or @tanstack imports

    Validates: Domain layer purity (no preact, react, @tanstack)
    """
    domain_dir = WEB_COMMONS / "domain"

    if not domain_dir.exists():
        pytest.skip("web/src/commons/domain does not exist")

    forbidden = ["preact", "react", "@tanstack", "@maintain-ux"]
    violations: List[str] = []

    for ts_file in domain_dir.rglob("*.ts"):
        try:
            content = ts_file.read_text()
        except Exception:
            continue

        for forbidden_import in forbidden:
            if f"from '{forbidden_import}" in content or f'from "{forbidden_import}' in content:
                rel_path = ts_file.relative_to(REPO_ROOT)
                violations.append(f"  - {rel_path}: imports {forbidden_import}")

    if violations:
        pytest.fail(
            f"\n\nFrontend domain layer should be framework-agnostic:\n" +
            "\n".join(violations)
        )


@pytest.mark.coder
def test_frontend_commons_has_index_files():
    """
    SPEC-CODER-COMMONS-0007: Frontend commons has proper barrel exports.

    GIVEN: web/src/commons directory
    WHEN: Checking for index.ts files
    THEN: Root and each layer has index.ts

    Validates: Public API structure
    """
    if not WEB_COMMONS.exists():
        pytest.skip("web/src/commons does not exist")

    expected_index_files = [
        WEB_COMMONS / "index.ts",
        WEB_COMMONS / "domain" / "index.ts",
        WEB_COMMONS / "application" / "index.ts",
        WEB_COMMONS / "integration" / "index.ts",
    ]

    missing = [f for f in expected_index_files if not f.exists()]

    if missing:
        pytest.fail(
            f"\n\nMissing index.ts barrel exports:\n" +
            "\n".join(f"  - {f.relative_to(REPO_ROOT)}" for f in missing)
        )


# ============================================================================
# PYTHON STRUCTURE VALIDATION (Feature-First)
# ============================================================================


@pytest.mark.coder
def test_python_commons_has_init_files():
    """
    SPEC-CODER-COMMONS-0008: Python commons has __init__.py files.

    GIVEN: python/commons directory
    WHEN: Checking for __init__.py files
    THEN: Root has __init__.py

    Validates: Python package structure
    """
    if not PYTHON_COMMONS.exists():
        pytest.skip("python/commons does not exist")

    init_file = PYTHON_COMMONS / "__init__.py"

    if not init_file.exists():
        pytest.fail(
            f"\n\nMissing __init__.py in python/commons/\n"
            f"Expected: {init_file.relative_to(REPO_ROOT)}"
        )


@pytest.mark.coder
def test_python_events_has_internal_layer_structure():
    """
    SPEC-CODER-COMMONS-0009: Python events feature has internal layer structure.

    GIVEN: python/commons/events directory
    WHEN: Checking for internal layers
    THEN: events/src/application/ports/ and events/src/integration/ exist

    Validates: Feature-first pattern for complex features
    """
    events_dir = PYTHON_COMMONS / "events"

    if not events_dir.exists():
        pytest.skip("python/commons/events does not exist")

    expected_paths = [
        events_dir / "src" / "application" / "ports",
        events_dir / "src" / "integration",
    ]

    missing = [p for p in expected_paths if not p.exists()]

    if missing:
        pytest.fail(
            f"\n\nPython events feature missing internal layer structure:\n" +
            "\n".join(f"  - {p.relative_to(REPO_ROOT)}" for p in missing) +
            f"\n\nExpected structure (feature-first with internal layers):\n" +
            "  python/commons/events/\n" +
            "  +-- src/\n" +
            "      +-- application/ports/   # EventBusPort\n" +
            "      +-- integration/         # Queues, adapters"
        )


@pytest.mark.coder
def test_python_resilience_is_flat():
    """
    SPEC-CODER-COMMONS-0010: Python resilience is flat (no internal layers).

    GIVEN: python/commons/resilience directory
    WHEN: Checking structure
    THEN: Contains .py files directly, no src/application/integration subdirs

    Validates: Flat structure for simple utilities
    """
    resilience_dir = PYTHON_COMMONS / "resilience"

    if not resilience_dir.exists():
        pytest.skip("python/commons/resilience does not exist")

    # Check that utility files exist at root
    expected_files = ["retry.py", "circuit_breaker.py"]
    missing_files = [f for f in expected_files if not (resilience_dir / f).exists()]

    # Check that no unnecessary layer subdirs exist
    unnecessary_subdirs = []
    for subdir in ["src", "application", "integration", "domain"]:
        if (resilience_dir / subdir).exists():
            unnecessary_subdirs.append(subdir)

    issues = []

    if missing_files:
        issues.append(
            f"Missing utility files: {', '.join(missing_files)}"
        )

    if unnecessary_subdirs:
        issues.append(
            f"Unnecessary layer subdirs (resilience should be flat): {', '.join(unnecessary_subdirs)}"
        )

    if issues:
        pytest.fail(
            f"\n\nPython resilience structure issues:\n" +
            "\n".join(f"  - {i}" for i in issues) +
            f"\n\nExpected structure (flat for simple utilities):\n" +
            "  python/commons/resilience/\n" +
            "  +-- __init__.py\n" +
            "  +-- retry.py\n" +
            "  +-- circuit_breaker.py"
        )


@pytest.mark.coder
def test_python_domain_no_framework_imports():
    """
    SPEC-CODER-COMMONS-0011: Python domain layer has no framework imports.

    GIVEN: Files in python/commons/domain/ and python/commons/validation.py
    WHEN: Checking import statements
    THEN: No flask, fastapi, or django imports

    Validates: Domain layer purity (no flask, fastapi, django)
    """
    if not PYTHON_COMMONS.exists():
        pytest.skip("python/commons does not exist")

    forbidden = ["flask", "fastapi", "django", "sqlalchemy", "requests"]
    violations: List[str] = []

    # Check domain directory
    domain_dir = PYTHON_COMMONS / "domain"
    if domain_dir.exists():
        for py_file in domain_dir.rglob("*.py"):
            _check_python_file_for_framework_imports(py_file, forbidden, violations)

    # Check validation.py (also domain layer)
    validation_file = PYTHON_COMMONS / "validation.py"
    if validation_file.exists():
        _check_python_file_for_framework_imports(validation_file, forbidden, violations)

    if violations:
        pytest.fail(
            f"\n\nPython domain layer should be framework-agnostic:\n" +
            "\n".join(violations)
        )


def _check_python_file_for_framework_imports(
    file_path: Path, forbidden: List[str], violations: List[str]
) -> None:
    """Check a Python file for framework imports."""
    try:
        content = file_path.read_text()
    except Exception:
        return

    for forbidden_import in forbidden:
        patterns = [
            rf"^import\s+{forbidden_import}",
            rf"^from\s+{forbidden_import}",
        ]
        for pattern in patterns:
            if re.search(pattern, content, re.MULTILINE):
                rel_path = file_path.relative_to(REPO_ROOT)
                violations.append(f"  - {rel_path}: imports {forbidden_import}")
                break


# ============================================================================
# STRUCTURAL PATTERN DOCUMENTATION
# ============================================================================


@pytest.mark.coder
def test_structural_patterns_documented():
    """
    SPEC-CODER-COMMONS-0012: Structural patterns are documented in convention.

    GIVEN: commons.convention.yaml
    WHEN: Checking for structure_patterns section
    THEN: Both python (feature-first) and frontend (layer-first) patterns documented

    Validates: Convention documents intentional divergence
    """
    convention_file = REPO_ROOT / "atdd" / "coder" / "conventions" / "commons.convention.yaml"

    if not convention_file.exists():
        pytest.fail(
            f"\n\nMissing convention file:\n"
            f"  - {convention_file.relative_to(REPO_ROOT)}"
        )

    content = convention_file.read_text()

    required_sections = [
        "structure_patterns:",
        "feature-first",
        "layer-first",
        "divergence_rationale:",
    ]

    missing = [s for s in required_sections if s not in content]

    if missing:
        pytest.fail(
            f"\n\nConvention file missing structural pattern documentation:\n" +
            "\n".join(f"  - {s}" for s in missing) +
            f"\n\nThe intentional divergence between Python (feature-first) and\n"
            f"Frontend (layer-first) should be documented in commons.convention.yaml"
        )
