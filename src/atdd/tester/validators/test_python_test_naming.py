"""
Test Python test files follow naming conventions.

Validates:
- Test files are named test_*.py
- Test files are in test/ or tests/ directories (accept both singular and plural)
- Test files have mandatory slugs (test_{wmbt}_{harness}_{nnn}_{slug}.py)
- Test functions start with test_
- Test classes start with Test

Inspired by: .claude/utils/tester/filename.py
But: Self-contained, no utility dependencies
"""

import pytest
import re
from pathlib import Path


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_DIR = REPO_ROOT / "python"


def find_test_files() -> list:
    """
    Find all test files in python/ directory.

    Returns:
        List of Path objects pointing to test files
    """
    if not PYTHON_DIR.exists():
        return []

    test_files = []

    # Find test files
    for py_file in PYTHON_DIR.rglob("*.py"):
        # Check if in test directory or named test_*
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            test_files.append(py_file)

    return test_files


def extract_test_functions(file_path: Path) -> list:
    """
    Extract test function names from Python file.

    Args:
        file_path: Path to test file

    Returns:
        List of function names
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    # Match: def test_something(...):
    # or: async def test_something(...):
    functions = re.findall(r'(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content)

    return functions


def extract_test_classes(file_path: Path) -> list:
    """
    Extract test class names from Python file.

    Args:
        file_path: Path to test file

    Returns:
        List of class names
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    # Match: class TestSomething(...):
    classes = re.findall(r'class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[:\(]', content)

    return classes


@pytest.mark.tester
def test_python_test_files_named_correctly():
    """
    SPEC-TESTER-NAMING-0001: Python test files follow naming convention.

    Convention:
    - Test files must be named test_*.py
    - Test files should be in test/ or tests/ directories (both accepted)

    Given: Python test files
    When: Checking file names
    Then: All test files follow convention
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No Python test files found")

    violations = []

    for test_file in test_files:
        filename = test_file.name

        # Skip special pytest files
        if filename in ['conftest.py', '__init__.py']:
            continue

        # Check naming convention
        if not filename.startswith('test_') and not filename.endswith('_test.py'):
            violations.append(
                f"{test_file.relative_to(REPO_ROOT)}\\n"
                f"  Issue: Test file should be named test_*.py\\n"
                f"  Found: {filename}"
            )

        # Check if in test/ or tests/ directory (accept both singular and plural)
        if '/test/' not in str(test_file) and '/tests/' not in str(test_file):
            violations.append(
                f"{test_file.relative_to(REPO_ROOT)}\\n"
                f"  Issue: Test file should be in test/ or tests/ directory\\n"
                f"  Found: Not in test/ or tests/ directory"
            )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} naming violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.tester
def test_python_test_functions_named_correctly():
    """
    SPEC-TESTER-NAMING-0002: Python test functions follow naming convention.

    Convention:
    - Test functions must start with test_
    - Test functions should use snake_case
    - Test functions should be descriptive

    Given: Python test files
    When: Checking function names
    Then: All test functions follow convention
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No Python test files found")

    violations = []

    for test_file in test_files:
        functions = extract_test_functions(test_file)

        for func_name in functions:
            # Skip helper functions (private)
            if func_name.startswith('_'):
                continue

            # Skip fixture functions
            if func_name in ['setup', 'teardown', 'setup_class', 'teardown_class',
                            'setup_method', 'teardown_method']:
                continue

            # Check if test function follows convention
            if not func_name.startswith('test_'):
                # Not a test function (could be helper)
                continue

            # Check snake_case (allow uppercase for WMBT codes like E003, UNIT, etc.)
            # Pattern accepts: test_e003_unit_001_... OR test_E003_UNIT_001_...
            if not re.match(r'^test_[a-zA-Z0-9_]+$', func_name):
                violations.append(
                    f"{test_file.relative_to(REPO_ROOT)}\\n"
                    f"  Function: {func_name}\\n"
                    f"  Issue: Test function should start with test_ and use alphanumeric_underscore pattern"
                )

            # Check if too short
            if len(func_name) < 10:
                violations.append(
                    f"{test_file.relative_to(REPO_ROOT)}\\n"
                    f"  Function: {func_name}\\n"
                    f"  Issue: Test function name too short (should be descriptive)"
                )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} function naming violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.tester
def test_python_test_classes_named_correctly():
    """
    SPEC-TESTER-NAMING-0003: Python test classes follow naming convention.

    Convention:
    - Test classes must start with Test
    - Test classes should use PascalCase
    - Test classes should be descriptive

    Given: Python test files
    When: Checking class names
    Then: All test classes follow convention
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No Python test files found")

    violations = []

    for test_file in test_files:
        classes = extract_test_classes(test_file)

        for class_name in classes:
            # Skip if not a test class (could be helper)
            if not class_name.startswith('Test'):
                continue

            # Check PascalCase
            if not re.match(r'^Test[A-Z][a-zA-Z0-9]*$', class_name):
                violations.append(
                    f"{test_file.relative_to(REPO_ROOT)}\\n"
                    f"  Class: {class_name}\\n"
                    f"  Issue: Test class should use PascalCase after 'Test'"
                )

            # Check if too short
            if len(class_name) < 8:  # Test + at least 3 chars
                violations.append(
                    f"{test_file.relative_to(REPO_ROOT)}\\n"
                    f"  Class: {class_name}\\n"
                    f"  Issue: Test class name too short (should be descriptive)"
                )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} class naming violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.tester
def test_python_test_files_have_mandatory_slugs():
    """
    SPEC-TESTER-NAMING-0004: Python test files in feature-based structure have mandatory slugs.

    Convention (from filename.convention.yaml):
    - Pattern: test_{wmbt_lower}_{harness_lower}_{nnn}_{slug_snake}.py
    - Slug is MANDATORY (not optional)
    - Slug derived from acceptance.identity.purpose
    - Example: test_l001_unit_001_uuid_v7_generation_completes_within.py

    Given: Python test files in python/{wagon}/{feature}/test/ directories
    When: Checking file names
    Then: All test files include mandatory slug component
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No Python test files found")

    violations = []

    # Pattern: test_{wmbt}_{harness}_{nnn}_{slug}.py
    # WMBT: 1-4 letters (L, P, C, etc.) followed by 3 digits
    # Harness: unit, integration, load, http, e2e, etc.
    # NNN: 3 digits (001, 002, etc.)
    # Slug: descriptive snake_case (MANDATORY)
    slug_pattern = re.compile(
        r'^test_([a-z]\d{3})_([a-z]+)_(\d{3})_([a-z][a-z0-9_]+)\.py$'
    )

    for test_file in test_files:
        filename = test_file.name

        # Skip special pytest files and wagon-level tests
        if filename in ['conftest.py', '__init__.py', 'test_contracts.py', 'test_telemetry.py']:
            continue

        # Only check files in feature-based structure: python/{wagon}/{feature}/test/
        test_path_str = str(test_file)
        if '/python/' not in test_path_str or '/test/' not in test_path_str:
            continue

        # Check if in feature-based directory structure
        parts = test_file.parts
        try:
            python_idx = parts.index('python')
            # Feature-based: python/{wagon}/{feature}/test/
            if len(parts) > python_idx + 3 and parts[python_idx + 3] == 'test':
                # This is a feature-based test file
                match = slug_pattern.match(filename)

                if not match:
                    # Try to parse what we have
                    basic_pattern = re.compile(r'^test_([a-z]\d{3})_([a-z]+)_(\d{3})\.py$')
                    basic_match = basic_pattern.match(filename)

                    if basic_match:
                        wmbt = basic_match.group(1)
                        harness = basic_match.group(2)
                        nnn = basic_match.group(3)
                        violations.append(
                            f"{test_file.relative_to(REPO_ROOT)}\n"
                            f"  Issue: Missing mandatory slug component\n"
                            f"  Pattern: test_{{wmbt}}_{{harness}}_{{nnn}}_{{slug}}.py\n"
                            f"  Found: test_{wmbt}_{harness}_{nnn}.py (no slug)\n"
                            f"  Expected: test_{wmbt}_{harness}_{nnn}_<descriptive_slug>.py\n"
                            f"  Note: Slug must be derived from acceptance.identity.purpose"
                        )
                    else:
                        violations.append(
                            f"{test_file.relative_to(REPO_ROOT)}\n"
                            f"  Issue: Does not match required pattern\n"
                            f"  Pattern: test_{{wmbt}}_{{harness}}_{{nnn}}_{{slug}}.py\n"
                            f"  Found: {filename}\n"
                            f"  Note: All 4 components required (wmbt, harness, nnn, slug)"
                        )
        except (ValueError, IndexError):
            # Not in feature-based structure, skip
            continue

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} test files without mandatory slugs:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            "\n\nSlug Convention:\n" +
            "- Slugs are MANDATORY (not optional)\n" +
            "- Derived from acceptance.identity.purpose field\n" +
            "- Process: Remove 'Verify', lowercase, replace spaces with underscores\n" +
            "- Example: 'Verify UUID v7 generation completes within' → 'uuid_v7_generation_completes_within'"
        )


@pytest.mark.tester
def test_python_test_files_are_in_correct_locations():
    """
    SPEC-TESTER-NAMING-0004: Test files are in correct locations.

    Convention:
    - Test files should be in {module}/test/ directory
    - Test files should mirror source structure when possible

    Given: Python test files
    When: Checking locations
    Then: Test files are in appropriate test/ directories
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No Python test files found")

    violations = []

    for test_file in test_files:
        # Check if in test/ or tests/ directory (accept both)
        if '/test/' not in str(test_file) and '/tests/' not in str(test_file):
            violations.append(
                f"{test_file.relative_to(REPO_ROOT)}\\n"
                f"  Issue: Test file not in test/ or tests/ directory"
            )

        # Check if test file has corresponding source structure
        # Example: module/test/test_foo.py should have module/src/foo.py
        # Accept both test/ and tests/ directories
        if ('/test/' in str(test_file) or '/tests/' in str(test_file)) and test_file.name.startswith('test_'):
            # Get potential source file name
            source_name = test_file.name.replace('test_', '', 1)
            test_dir = test_file.parent

            # Check for src/ sibling
            module_root = test_dir.parent
            src_dir = module_root / 'src'

            if src_dir.exists():
                # Look for corresponding source file
                potential_source = src_dir / source_name
                # Also check subdirectories (domain, application, etc.)
                source_exists = potential_source.exists() or \
                              any((src_dir / subdir / source_name).exists()
                                  for subdir in ['domain', 'application', 'integration', 'presentation'])

                if not source_exists and source_name != '__init__.py':
                    # This might be okay (integration tests, etc.) so just warn
                    pass  # Don't fail, just note

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} location violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )
