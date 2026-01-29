"""
Test that tests don't interfere with each other.

Validates:
- Tests don't share mutable state
- Fixtures are properly scoped
- Tests can run in parallel safely
- No test pollution (side effects)

Inspired by: .claude/utils/tester/isolation.py
But: Self-contained, no utility dependencies
"""

import pytest
import re
import ast
from pathlib import Path
from typing import List, Set, Tuple


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
TEST_DIRS = [
    REPO_ROOT / "test",
    REPO_ROOT / "tests",
    REPO_ROOT / "atdd",
]


def find_test_files() -> List[Path]:
    """
    Find all test files.

    Returns:
        List of Path objects
    """
    test_files = []

    for test_dir in TEST_DIRS:
        if not test_dir.exists():
            continue

        # Python tests
        for py_test in test_dir.rglob("test_*.py"):
            if '__pycache__' not in str(py_test):
                test_files.append(py_test)

        for py_test in test_dir.rglob("*_test.py"):
            if '__pycache__' not in str(py_test):
                test_files.append(py_test)

    return test_files


def extract_global_variables(file_path: Path) -> List[str]:
    """
    Extract global variable assignments from Python test file.

    Args:
        file_path: Path to test file

    Returns:
        List of global variable names
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    globals_list = []

    for node in ast.walk(tree):
        # Top-level assignments
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    # Skip constants (UPPER_CASE)
                    if not name.isupper():
                        # Skip if it's in a function/class
                        for parent in ast.walk(tree):
                            if isinstance(parent, (ast.FunctionDef, ast.ClassDef)):
                                if node in ast.walk(parent):
                                    break
                        else:
                            # It's a top-level mutable global
                            globals_list.append(name)

    return globals_list


def extract_fixture_scopes(file_path: Path) -> List[Tuple[str, str]]:
    """
    Extract pytest fixtures and their scopes.

    Args:
        file_path: Path to test file

    Returns:
        List of (fixture_name, scope) tuples
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    fixtures = []

    # Match @pytest.fixture or @pytest.fixture(scope="...")
    fixture_pattern = r'@pytest\.fixture(?:\(scope=["\'](\w+)["\']\))?'
    
    lines = content.split('\n')
    for i, line in enumerate(lines):
        match = re.search(fixture_pattern, line)
        if match:
            scope = match.group(1) or 'function'  # Default scope is 'function'
            
            # Get function name from next lines
            for j in range(i+1, min(i+5, len(lines))):
                func_match = re.match(r'\s*def\s+(\w+)\s*\(', lines[j])
                if func_match:
                    fixture_name = func_match.group(1)
                    fixtures.append((fixture_name, scope))
                    break

    return fixtures


def check_for_file_mutations(file_path: Path) -> List[str]:
    """
    Check if test file mutates global state (files, environment, etc.).

    Uses AST to detect actual code mutations, avoiding false positives
    from patterns in strings/comments/docstrings.

    Skips file write/delete checks if test functions use tmp_path fixture.

    Args:
        file_path: Path to test file

    Returns:
        List of mutation violations
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    violations = set()

    # Check if any test function uses tmp_path or similar temp directory fixtures
    # Common fixture names that indicate temp directory usage
    TEMP_FIXTURES = {'tmp_path', 'tmp_path_factory', 'temp_repo', 'temp_dir', 'tmpdir'}
    uses_tmp_path = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
            for arg in node.args.args:
                if arg.arg in TEMP_FIXTURES:
                    uses_tmp_path = True
                    break
        if uses_tmp_path:
            break

    for node in ast.walk(tree):
        # Check for sys.path.insert/append calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                # sys.path.insert(...) or sys.path.append(...)
                if node.func.attr in ('insert', 'append'):
                    if isinstance(node.func.value, ast.Attribute):
                        if (node.func.value.attr == 'path' and
                            isinstance(node.func.value.value, ast.Name) and
                            node.func.value.value.id == 'sys'):
                            violations.add('sys.path mutation (use monkeypatch fixture)')

                # os.remove(...) or shutil.rmtree(...) - skip if using tmp_path
                if not uses_tmp_path:
                    if node.func.attr == 'remove':
                        if isinstance(node.func.value, ast.Name) and node.func.value.id == 'os':
                            violations.add('File deletion without fixture (should use tmp_path)')
                    if node.func.attr == 'rmtree':
                        if isinstance(node.func.value, ast.Name) and node.func.value.id == 'shutil':
                            violations.add('File deletion without fixture (should use tmp_path)')

        # Check for os.environ[...] = ... (subscript assignment)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    if isinstance(target.value, ast.Attribute):
                        if (target.value.attr == 'environ' and
                            isinstance(target.value.value, ast.Name) and
                            target.value.value.id == 'os'):
                            violations.add('Direct os.environ mutation (use monkeypatch fixture)')

        # Check for open(..., 'w') - skip if using tmp_path fixture
        if not uses_tmp_path:
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'open':
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            if 'w' in arg.value:
                                violations.add('File write without fixture (should use tmp_path)')
                    for kw in node.keywords:
                        if kw.arg == 'mode' and isinstance(kw.value, ast.Constant):
                            if 'w' in str(kw.value.value):
                                violations.add('File write without fixture (should use tmp_path)')

    return list(violations)


def check_for_shared_state(file_path: Path) -> List[str]:
    """
    Check for mutable shared state between tests.

    Args:
        file_path: Path to test file

    Returns:
        List of shared state violations
    """
    globals_vars = extract_global_variables(file_path)
    
    violations = []
    
    # Filter out common test globals that are OK
    ALLOWED_GLOBALS = {
        'pytestmark',  # Pytest markers
        'REPO_ROOT',   # Path constants
        'TEST_DIR',
        'PROJECT_ROOT',
    }
    
    for var_name in globals_vars:
        if var_name not in ALLOWED_GLOBALS and not var_name.startswith('_'):
            violations.append(
                f"Mutable global variable '{var_name}' (use fixture instead)"
            )
    
    return violations


@pytest.mark.tester
def test_no_mutable_global_state():
    """
    SPEC-TESTER-ISOLATION-0001: Tests don't use mutable global state.

    Tests should not share mutable state via global variables.
    Use fixtures for shared setup instead.

    Violations:
    - Global mutable variables (lists, dicts, objects)
    - Module-level state that can be modified

    OK:
    - Constants (UPPER_CASE)
    - Path constants (REPO_ROOT, etc.)
    - Pytest markers (pytestmark)

    Given: Test files in test/, tests/, atdd/
    When: Checking for global variables
    Then: No mutable global state
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No test files found to validate")

    violations = []

    for test_file in test_files:
        shared_state_violations = check_for_shared_state(test_file)
        
        if shared_state_violations:
            rel_path = test_file.relative_to(REPO_ROOT)
            for violation in shared_state_violations:
                violations.append(
                    f"{rel_path}\n"
                    f"  Issue: {violation}"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} mutable global state violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\n\nTests should not use mutable global variables.\n" +
            f"Use pytest fixtures for shared setup/teardown."
        )


@pytest.mark.tester
def test_fixtures_have_appropriate_scope():
    """
    SPEC-TESTER-ISOLATION-0002: Fixtures have appropriate scope.

    Fixture scopes:
    - function: Default, runs for each test (isolated)
    - class: Shared within test class
    - module: Shared within module
    - session: Shared across entire test session

    Best practices:
    - Use 'function' scope by default (isolation)
    - Use broader scopes only for expensive, read-only resources
    - Never use session/module scope for mutable fixtures

    Given: Fixtures in test files
    When: Checking fixture scopes
    Then: Appropriate scopes for isolation
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No test files found to validate")

    violations = []

    # Fixtures that should typically be function-scoped
    SHOULD_BE_FUNCTION_SCOPED = {
        'mock', 'mocker', 'patch', 'temp', 'tmp', 'data', 'user', 'session', 'state'
    }

    for test_file in test_files:
        fixtures = extract_fixture_scopes(test_file)
        
        for fixture_name, scope in fixtures:
            # Check if fixture name suggests it should be function-scoped
            name_lower = fixture_name.lower()
            
            for keyword in SHOULD_BE_FUNCTION_SCOPED:
                if keyword in name_lower and scope != 'function':
                    rel_path = test_file.relative_to(REPO_ROOT)
                    violations.append(
                        f"{rel_path}\n"
                        f"  Fixture: {fixture_name}\n"
                        f"  Current Scope: {scope}\n"
                        f"  Issue: Fixture name suggests mutable state, should use 'function' scope"
                    )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} fixture scope violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\n\nFixtures with mutable state should use 'function' scope.\n" +
            f"Only use broader scopes for expensive, immutable resources."
        )


@pytest.mark.tester
def test_no_direct_environment_mutations():
    """
    SPEC-TESTER-ISOLATION-0003: Tests don't directly mutate environment.

    Tests should not directly mutate:
    - Environment variables (use monkeypatch)
    - System paths (use monkeypatch)
    - File system (use tmp_path or tmp_dir fixtures)
    - Global config (use fixtures)

    Given: Test files
    When: Checking for direct mutations
    Then: All mutations use proper fixtures
    """
    # Auto-fix validators that intentionally modify repo files
    AUTOFIX_VALIDATORS = {
        'test_init_file_urns.py',  # Auto-fixes URN headers in __init__.py files
    }

    test_files = find_test_files()

    if not test_files:
        pytest.skip("No test files found to validate")

    violations = []

    for test_file in test_files:
        # Skip auto-fix validators (they intentionally write to repo files)
        if test_file.name in AUTOFIX_VALIDATORS:
            continue

        mutation_violations = check_for_file_mutations(test_file)
        
        if mutation_violations:
            rel_path = test_file.relative_to(REPO_ROOT)
            for violation in mutation_violations:
                violations.append(
                    f"{rel_path}\n"
                    f"  Issue: {violation}"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} environment mutation violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\n\nTests should use fixtures for environment mutations:\n" +
            f"  - Use monkeypatch for os.environ, sys.path\n" +
            f"  - Use tmp_path for file operations\n" +
            f"  - Use fixtures for cleanup"
        )


@pytest.mark.tester
def test_tests_can_run_in_parallel():
    """
    SPEC-TESTER-ISOLATION-0004: Tests can safely run in parallel.

    Tests should be parallelizable unless explicitly marked.
    Use pytest.mark.serial for tests that must run sequentially.

    Indicators of parallel-safe tests:
    - No shared mutable state
    - No file system mutations (or use tmp_path)
    - No environment mutations (or use monkeypatch)
    - No timing dependencies

    Given: Test files
    When: Checking for parallel safety
    Then: Tests marked appropriately for parallelism
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No test files found to validate")

    violations = []

    for test_file in test_files:
        # Check if file has pytestmark = pytest.mark.serial
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        has_serial_marker = 'pytest.mark.serial' in content

        # Check for parallelism violations
        parallel_violations = []
        
        # Check for shared state
        shared_state = check_for_shared_state(test_file)
        if shared_state:
            parallel_violations.extend(shared_state)
        
        # Check for file mutations
        mutations = check_for_file_mutations(test_file)
        if mutations:
            # File mutations are OK if using tmp_path, but flag others
            dangerous_mutations = [m for m in mutations if 'tmp_path' not in m]
            if dangerous_mutations:
                parallel_violations.extend(dangerous_mutations)

        # If has violations but no serial marker
        if parallel_violations and not has_serial_marker:
            rel_path = test_file.relative_to(REPO_ROOT)
            violations.append(
                f"{rel_path}\n"
                f"  Issues: {len(parallel_violations)} parallel-safety violations\n"
                f"  Violations:\n" +
                "\n".join(f"    - {v}" for v in parallel_violations[:3]) +
                f"  Suggestion: Add 'pytestmark = pytest.mark.serial' if tests must run sequentially"
            )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} parallelism violations:\n\n" +
            "\n\n".join(violations[:5]) +
            (f"\n\n... and {len(violations) - 5} more" if len(violations) > 5 else "") +
            f"\n\nTests should either:\n" +
            f"  1. Be parallel-safe (no shared state, use fixtures)\n" +
            f"  2. Be marked with pytest.mark.serial"
        )
