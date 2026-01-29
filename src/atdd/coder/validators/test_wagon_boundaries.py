"""
Test wagon boundary isolation via qualified imports.

Validates conventions from:
- atdd/coder/conventions/boundaries.convention.yaml

Enforces:
- No bare layer imports (from domain.X import Y)
- No sys.path manipulation in test files
- No cross-wagon imports (wagon A importing wagon B)
- Qualified imports pattern (from {wagon}.{feature}.src.{layer}.{module} import Class)
- Package hierarchy exists (__init__.py files)
- pytest pythonpath configured

Rationale:
Multiple wagons use identical layer names (domain, application, integration).
Without qualified imports, Python cannot distinguish between:
  - commit_state/sign_commit/src/domain/signature_algorithm.py
  - juggle_domains/score_domains/src/domain/choice.py

Both would resolve to "domain.X" causing module shadowing when tests run together.
"""

import pytest
import re
from pathlib import Path
from typing import List, Tuple, Set
import ast


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_DIR = REPO_ROOT / "python"
PYPROJECT_TOML = PYTHON_DIR / "pyproject.toml"
BOUNDARIES_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "boundaries.convention.yaml"


def find_test_files() -> List[Path]:
    """Find all test files in wagons."""
    if not PYTHON_DIR.exists():
        return []

    test_files = []
    for py_file in PYTHON_DIR.rglob("test_*.py"):
        # Skip __pycache__
        if '__pycache__' in str(py_file):
            continue
        test_files.append(py_file)

    return test_files


def find_implementation_files() -> List[Path]:
    """
    Find all implementation files in wagons (excluding tests and orchestration layers).

    Excluded from wagon boundary checks:
    - Test files (testing infrastructure)
    - wagon.py, composition.py (wagon-level orchestration)
    - shared/ directory (theme/train-level orchestration)
    - contracts/ directory (neutral DTO boundary layer)
    - scripts/ directory (utility scripts and tools)
    """
    if not PYTHON_DIR.exists():
        return []

    impl_files = []
    for py_file in PYTHON_DIR.rglob("*.py"):
        # Skip test files
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            continue
        # Skip __pycache__
        if '__pycache__' in str(py_file):
            continue
        # Skip wagon.py, composition.py, and game.py (wagon/app-level orchestration)
        if py_file.name in ['wagon.py', 'composition.py', 'game.py']:
            continue
        # Skip shared/ directory (theme/train-level orchestration - can import across wagons)
        if '/shared/' in str(py_file):
            continue
        # Skip contracts/ directory (neutral DTO layer)
        if '/contracts/' in str(py_file):
            continue
        # Skip scripts/ directory (utility scripts - can import across wagons for tooling)
        if '/scripts/' in str(py_file):
            continue

        impl_files.append(py_file)

    return impl_files


def extract_imports_ast(file_path: Path) -> List[Tuple[str, int]]:
    """
    Extract imports using AST parsing.

    Excludes imports that are:
    - Inside `if TYPE_CHECKING:` blocks (type-only imports, never executed)
    - Inside function/method definitions (lazy imports for architecture compliance)

    Returns:
        List of (import_path, line_number) tuples
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    imports = []

    try:
        tree = ast.parse(content, filename=str(file_path))

        def is_inside_type_checking(node, tree):
            """Check if node is inside an 'if TYPE_CHECKING:' block."""
            for parent in ast.walk(tree):
                if isinstance(parent, ast.If):
                    # Check if condition is TYPE_CHECKING
                    if isinstance(parent.test, ast.Name) and parent.test.id == 'TYPE_CHECKING':
                        # Check if the import node is in the body of this if
                        for child in ast.walk(parent):
                            if child is node:
                                return True
            return False

        def is_inside_function(node, tree):
            """Check if node is inside a function/method definition."""
            for parent in ast.walk(tree):
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for child in ast.walk(parent):
                        if child is node:
                            return True
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:  # Only absolute imports (not relative imports with ...)
                    # Skip TYPE_CHECKING and function-level imports
                    if not is_inside_type_checking(node, tree) and not is_inside_function(node, tree):
                        imports.append((node.module, node.lineno))
            elif isinstance(node, ast.Import):
                # Skip TYPE_CHECKING and function-level imports
                if not is_inside_type_checking(node, tree) and not is_inside_function(node, tree):
                    for alias in node.names:
                        imports.append((alias.name, node.lineno))
    except SyntaxError:
        # Fall back to regex if AST parsing fails
        return extract_imports_regex(file_path)

    return imports


def extract_imports_regex(file_path: Path) -> List[Tuple[str, int]]:
    """Extract imports using regex (fallback)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return []

    imports = []

    for line_no, line in enumerate(lines, start=1):
        # from X import Y
        match = re.match(r'from\s+([^\s]+)\s+import', line)
        if match:
            imports.append((match.group(1), line_no))

        # import X
        match = re.match(r'^\s*import\s+([^\s;#]+)', line)
        if match:
            for imp in match.group(1).split(','):
                imports.append((imp.strip(), line_no))

    return imports


def check_for_syspath_manipulation(file_path: Path) -> List[Tuple[str, int]]:
    """
    Check if file manipulates sys.path.

    Returns:
        List of (line_content, line_number) tuples where sys.path is manipulated
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return []

    violations = []

    for line_no, line in enumerate(lines, start=1):
        if 'sys.path.insert' in line or 'sys.path.append' in line:
            violations.append((line.strip(), line_no))

    return violations


def get_wagon_from_path(file_path: Path) -> str:
    """Extract wagon name from file path."""
    try:
        rel_path = file_path.relative_to(PYTHON_DIR)
        parts = rel_path.parts
        if len(parts) > 0:
            return parts[0]
    except ValueError:
        pass
    return ""


def is_bare_layer_import(import_path: str) -> bool:
    """
    Check if import is a bare layer import.

    Bare imports like:
    - from domain.X import Y
    - from application.X import Y
    - from integration.X import Y
    - from presentation.X import Y

    Returns:
        True if bare layer import
    """
    # Check if starts with layer name (and not a qualified path)
    if import_path.startswith(('domain.', 'application.', 'integration.', 'presentation.')):
        return True

    # Check exact match (import domain, import application, etc.)
    if import_path in ['domain', 'application', 'integration', 'presentation']:
        return True

    return False


def is_cross_wagon_import(file_path: Path, import_path: str) -> Tuple[bool, str, str]:
    """
    Check if import crosses wagon boundaries.

    Returns:
        (is_cross_wagon, source_wagon, target_wagon)
    """
    source_wagon = get_wagon_from_path(file_path)

    # Check if import is from a different wagon
    # Pattern: {wagon}.{feature}.src.{layer}.{module}
    match = re.match(r'([^.]+)\.', import_path)
    if match:
        target_wagon = match.group(1)

        # Check if it's a different wagon (not shared utilities, commons, or contracts)
        # generate_identifiers is a utility wagon providing cross-cutting concerns
        if target_wagon != source_wagon and target_wagon not in ['shared', 'commons', 'generate_identifiers', '__init__', 'contracts']:
            # Verify it's an actual wagon directory
            wagon_dir = PYTHON_DIR / target_wagon
            if wagon_dir.exists() and wagon_dir.is_dir():
                return (True, source_wagon, target_wagon)

    return (False, source_wagon, "")


def check_package_hierarchy() -> List[str]:
    """
    Check if required __init__.py files exist for package hierarchy.

    Returns:
        List of missing __init__.py paths
    """
    missing = []

    # Check python/__init__.py
    if not (PYTHON_DIR / "__init__.py").exists():
        missing.append("python/__init__.py")

    # Check each wagon
    for wagon_dir in PYTHON_DIR.iterdir():
        if not wagon_dir.is_dir() or wagon_dir.name.startswith('.') or wagon_dir.name == '__pycache__':
            continue

        # Check wagon/__init__.py
        if not (wagon_dir / "__init__.py").exists():
            missing.append(f"python/{wagon_dir.name}/__init__.py")

        # Check each feature in wagon
        for feature_dir in wagon_dir.iterdir():
            if not feature_dir.is_dir() or feature_dir.name.startswith('.') or feature_dir.name == '__pycache__':
                continue

            # Skip non-feature directories
            if feature_dir.name in ['__pycache__', 'test', 'tests']:
                continue

            # Check if has src/ (indicates it's a feature)
            src_dir = feature_dir / "src"
            if src_dir.exists():
                # Check feature/__init__.py
                if not (feature_dir / "__init__.py").exists():
                    missing.append(f"python/{wagon_dir.name}/{feature_dir.name}/__init__.py")

    return missing


def check_pytest_pythonpath() -> Tuple[bool, str]:
    """
    Check if pytest pythonpath is configured in pyproject.toml.

    Returns:
        (is_configured, message)
    """
    if not PYPROJECT_TOML.exists():
        return (False, "python/pyproject.toml not found")

    try:
        with open(PYPROJECT_TOML, 'r') as f:
            content = f.read()

        # Check for [tool.pytest.ini_options] section with pythonpath
        if 'tool.pytest.ini_options' in content and 'pythonpath' in content:
            return (True, "pythonpath configured")
        else:
            return (False, "pythonpath not configured in [tool.pytest.ini_options]")
    except Exception as e:
        return (False, f"Error reading pyproject.toml: {e}")


@pytest.mark.coder
def test_no_bare_layer_imports_in_tests():
    """
    SPEC-BOUNDARIES-0001: Test files must use qualified imports.

    Convention: boundaries.convention.yaml::namespacing.forbidden_patterns.bare_layer_imports

    Forbidden:
    - from domain.signature_algorithm import SignatureAlgorithm
    - from application.use_cases.X import Y

    Required:
    - from commit_state.sign_commit.src.domain.signature_algorithm import SignatureAlgorithm
    - from juggle_domains.score_domains.src.application.use_cases.X import Y

    Given: All test files in python/
    When: Checking imports
    Then: No bare layer imports (from domain.X, from application.X, etc.)
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No test files found to validate")

    violations = []

    for test_file in test_files:
        imports = extract_imports_ast(test_file)

        for import_path, line_no in imports:
            if is_bare_layer_import(import_path):
                rel_path = test_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{line_no}\n"
                    f"  Import: from {import_path} import ...\n"
                    f"  Issue: Bare layer import causes module shadowing\n"
                    f"  Fix: Use qualified import from {{wagon}}.{{feature}}.src.{import_path.split('.')[0]}.{{module}}"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} bare layer imports in test files:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            "\n\nSee: atdd/coder/conventions/boundaries.convention.yaml::namespacing.forbidden_patterns"
        )


@pytest.mark.coder
def test_no_syspath_manipulation_in_tests():
    """
    SPEC-BOUNDARIES-0002: Test files must not manipulate sys.path.

    Convention: boundaries.convention.yaml::namespacing.syspath_prohibition

    Forbidden in test files:
    - sys.path.insert(0, str(src_path))
    - sys.path.append(...)

    Reason: Causes cross-wagon path collisions; use pytest pythonpath instead

    Given: All test files
    When: Checking for sys.path manipulation
    Then: No sys.path.insert() or sys.path.append() in test files
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No test files found to validate")

    violations = []

    for test_file in test_files:
        syspath_lines = check_for_syspath_manipulation(test_file)

        if syspath_lines:
            rel_path = test_file.relative_to(REPO_ROOT)
            for line_content, line_no in syspath_lines:
                violations.append(
                    f"{rel_path}:{line_no}\n"
                    f"  Code: {line_content}\n"
                    f"  Issue: Test file manipulates sys.path\n"
                    f"  Fix: Remove sys.path manipulation; pytest pythonpath handles this"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} sys.path manipulations in test files:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            "\n\nSee: atdd/coder/conventions/boundaries.convention.yaml::namespacing.syspath_prohibition"
        )


@pytest.mark.coder
def test_no_cross_wagon_imports():
    """
    SPEC-BOUNDARIES-0003: Wagons cannot import directly from other wagons.

    Convention: boundaries.convention.yaml::interaction.forbidden_cross_wagon_imports
    Cross-reference: design.convention.yaml::VC-DS-06

    Forbidden:
    - from juggle_domains.score_domains.src.domain.choice import Choice  # in commit_state wagon

    Required:
    - Wagons communicate only via contracts (see contract.convention.yaml)

    Given: All implementation files
    When: Checking imports
    Then: No imports from other wagons (only via contracts)
    """
    impl_files = find_implementation_files()

    if not impl_files:
        pytest.skip("No implementation files found to validate")

    violations = []

    for impl_file in impl_files:
        imports = extract_imports_ast(impl_file)

        for import_path, line_no in imports:
            is_cross, source_wagon, target_wagon = is_cross_wagon_import(impl_file, import_path)

            if is_cross:
                rel_path = impl_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{line_no}\n"
                    f"  Source wagon: {source_wagon}\n"
                    f"  Target wagon: {target_wagon}\n"
                    f"  Import: {import_path}\n"
                    f"  Issue: Direct cross-wagon import creates tight coupling\n"
                    f"  Fix: Use contracts for wagon-to-wagon communication"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} cross-wagon imports:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            "\n\nSee: atdd/coder/conventions/boundaries.convention.yaml::interaction.forbidden_cross_wagon_imports"
        )


@pytest.mark.coder
def test_package_hierarchy_exists():
    """
    SPEC-BOUNDARIES-0004: Package hierarchy must be complete.

    Convention: boundaries.convention.yaml::namespacing.package_hierarchy

    Required __init__.py files:
    - python/__init__.py
    - python/{wagon}/__init__.py
    - python/{wagon}/{feature}/__init__.py

    Given: Python directory structure
    When: Checking for __init__.py files
    Then: All required __init__.py files exist
    """
    missing = check_package_hierarchy()

    if missing:
        pytest.fail(
            f"\n\nMissing {len(missing)} required __init__.py files:\n\n" +
            "\n".join(f"  - {path}" for path in missing) +
            "\n\nPackage hierarchy is required for qualified imports to work.\n" +
            "See: atdd/coder/conventions/boundaries.convention.yaml::namespacing.package_hierarchy"
        )


@pytest.mark.coder
def test_pytest_pythonpath_configured():
    """
    SPEC-BOUNDARIES-0005: pytest pythonpath must be configured.

    Convention: boundaries.convention.yaml::namespacing.test_configuration

    Required in python/pyproject.toml:
    [tool.pytest.ini_options]
    pythonpath = ["."]

    Given: python/pyproject.toml
    When: Checking [tool.pytest.ini_options]
    Then: pythonpath = ["."] is configured
    """
    is_configured, message = check_pytest_pythonpath()

    if not is_configured:
        pytest.fail(
            f"\n\npytest pythonpath not configured:\n\n"
            f"  Issue: {message}\n\n"
            f"Required configuration in python/pyproject.toml:\n"
            f"  [tool.pytest.ini_options]\n"
            f"  pythonpath = [\".\"]\n\n"
            f"This is required for qualified imports to work across wagons.\n"
            f"See: atdd/coder/conventions/boundaries.convention.yaml::namespacing.test_configuration"
        )


@pytest.mark.coder
def test_no_bare_layer_imports_in_implementation():
    """
    SPEC-BOUNDARIES-0006: Implementation files should use qualified imports.

    Convention: boundaries.convention.yaml::namespacing.forbidden_patterns.bare_layer_imports

    Note: composition.py and wagon.py are excluded (they may use bare imports)

    Forbidden in implementation files:
    - from domain.signature_algorithm import SignatureAlgorithm
    - from src.domain.X import Y

    Required:
    - from commit_state.sign_commit.src.domain.signature_algorithm import SignatureAlgorithm
    - Relative imports within same layer: from .base_repository import BaseRepository

    Given: All implementation files (excluding composition.py/wagon.py)
    When: Checking imports
    Then: No bare layer imports or src-relative imports
    """
    impl_files = find_implementation_files()

    if not impl_files:
        pytest.skip("No implementation files found to validate")

    violations = []

    for impl_file in impl_files:
        imports = extract_imports_ast(impl_file)

        for import_path, line_no in imports:
            # Check for bare layer imports
            if is_bare_layer_import(import_path):
                rel_path = impl_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{line_no}\n"
                    f"  Import: from {import_path} import ...\n"
                    f"  Issue: Bare layer import in implementation file\n"
                    f"  Fix: Use qualified import or relative import within same layer"
                )

            # Check for src-relative imports
            elif import_path.startswith('src.'):
                rel_path = impl_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{line_no}\n"
                    f"  Import: from {import_path} import ...\n"
                    f"  Issue: src-relative import only works with sys.path manipulation\n"
                    f"  Fix: Use qualified import from {{wagon}}.{{feature}}.src.{{layer}}.{{module}}"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} bare/src-relative imports in implementation:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            "\n\nSee: atdd/coder/conventions/boundaries.convention.yaml::namespacing.forbidden_patterns"
        )
