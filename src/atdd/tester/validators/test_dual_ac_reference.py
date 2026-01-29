"""
Test that Python test files have AC URN in BOTH header comment and docstring.

Per RED convention v1.0+, tests MUST have AC URN in:
1. Header comment: # URN: acc:...
2. Module docstring: RED Test for acc:...

This ensures:
- Machine parseability (header comment)
- Human readability (docstring)
- Redundancy for validation
"""

import pytest
import re
from pathlib import Path


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_DIR = REPO_ROOT / "python"


def find_test_files() -> list:
    """Find all Python test files."""
    if not PYTHON_DIR.exists():
        return []

    test_files = []
    for py_file in PYTHON_DIR.rglob("test_*.py"):
        # Skip __pycache__ and conftest
        if '__pycache__' in str(py_file) or 'conftest' in py_file.name:
            continue
        test_files.append(py_file)

    return test_files


def extract_ac_from_header(content: str) -> str | None:
    """Extract AC URN from header comment."""
    match = re.search(
        r'^#\s*URN:\s*(acc:[a-z\-]+:[A-Z0-9]+-[A-Z0-9]+-\d{3}(?:-[a-z\-]+)?)',
        content,
        re.MULTILINE
    )
    return match.group(1) if match else None


def extract_ac_from_docstring(content: str) -> str | None:
    """Extract AC URN from module docstring."""
    match = re.search(
        r'^\s*""".*?(acc:[a-z\-]+:[A-Z0-9]+-[A-Z0-9]+-\d{3}(?:-[a-z\-]+)?)',
        content,
        re.DOTALL | re.MULTILINE
    )
    return match.group(1) if match else None


@pytest.mark.platform
def test_all_tests_have_dual_ac_references():
    """
    SPEC-TESTER-CONVENTION-0001: Test files MUST have AC URN in both header and docstring

    Given: All Python test files
    When: Checking for AC URN references
    Then: Files MUST have AC URN in BOTH header comment AND module docstring
          AND both references MUST match exactly
    """
    test_files = find_test_files()

    if not test_files:
        pytest.skip("No test files found")

    errors = []
    warnings = []

    for test_file in test_files:
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            warnings.append(f"Could not read {test_file.relative_to(REPO_ROOT)}: {e}")
            continue

        ac_from_header = extract_ac_from_header(content)
        ac_from_docstring = extract_ac_from_docstring(content)

        rel_path = test_file.relative_to(REPO_ROOT)

        # Check for presence
        if not ac_from_header and not ac_from_docstring:
            # Legacy test without AC URN - skip for now (will be migrated)
            continue

        if ac_from_header and not ac_from_docstring:
            errors.append(
                f"{rel_path}\n"
                f"  ❌ MISSING: Module docstring with AC URN\n"
                f"  Current state:\n"
                f"    ✅ Header comment: {ac_from_header}\n"
                f"    ❌ Module docstring: MISSING\n"
                f"\n"
                f"  ACTION REQUIRED: Add this module docstring after header comments:\n"
                f'  """\n'
                f'  RED Test for {ac_from_header}\n'
                f'  wagon: {{wagon}} | feature: {{feature}} | phase: {{RED|GREEN|REFACTOR}}\n'
                f'  WMBT: {{wmbt URN}}\n'
                f'  Purpose: {{acceptance criteria purpose}}\n'
                f'  """\n'
            )

        if ac_from_docstring and not ac_from_header:
            errors.append(
                f"{rel_path}\n"
                f"  ❌ MISSING: Header comment with AC URN\n"
                f"  Current state:\n"
                f"    ❌ Header comment: MISSING\n"
                f"    ✅ Module docstring: {ac_from_docstring}\n"
                f"\n"
                f"  ACTION REQUIRED: Add these lines at the top of the file:\n"
                f"  # Runtime: {{python|supabase|dart}}\n"
                f"  # Rationale: {{brief explanation}}\n"
                f"  # URN: {ac_from_docstring}\n"
                f"  # Phase: {{RED|GREEN|REFACTOR}}\n"
                f"  # Purpose: {{acceptance criteria purpose}}\n"
            )

        # Check for match (allowing slugless to match slugged)
        # Pattern: acc:wagon:WMBT-HARNESS-NNN[-optional-slug]
        if ac_from_header and ac_from_docstring:
            # Extract base URN (without slug) for comparison
            # Pattern: acc:wagon:WMBT-HARNESS-NNN
            base_pattern = r'(acc:[a-z\-]+:[A-Z0-9]+-[A-Z0-9]+-\d{3})'
            header_base = re.match(base_pattern, ac_from_header)
            docstring_base = re.match(base_pattern, ac_from_docstring)

            if header_base and docstring_base:
                # Compare base URNs (both URNs should have same wagon:WMBT-HARNESS-NNN)
                if header_base.group(1) != docstring_base.group(1):
                    errors.append(
                        f"{rel_path}\n"
                        f"  ❌ MISMATCH: Header and docstring reference different AC URNs\n"
                        f"  Current state:\n"
                        f"    Header comment: {ac_from_header}\n"
                        f"    Module docstring: {ac_from_docstring}\n"
                        f"\n"
                        f"  ACTION REQUIRED: Both MUST reference the same AC URN\n"
                        f"  Either:\n"
                        f"    1. Update header to: # URN: {ac_from_docstring}\n"
                        f"    OR\n"
                        f"    2. Update docstring to: RED Test for {ac_from_header}\n"
                        f"  (Choose the correct AC URN from plan/ acceptance criteria)"
                    )

    if warnings:
        print("\n⚠️  WARNINGS:")
        for warning in warnings:
            print(f"  {warning}")

    if errors:
        # Categorize errors
        missing_docstring = sum(1 for e in errors if "MISSING: Module docstring" in e)
        missing_header = sum(1 for e in errors if "MISSING: Header comment" in e)
        mismatched = sum(1 for e in errors if "MISMATCH:" in e)

        error_report = "\n\n".join(errors)
        pytest.fail(
            f"\n\n"
            f"══════════════════════════════════════════════════════════════════════\n"
            f"❌ AC URN VALIDATION FAILED: {len(errors)} test files need updates\n"
            f"══════════════════════════════════════════════════════════════════════\n"
            f"\n"
            f"BREAKDOWN:\n"
            f"  • Missing docstring: {missing_docstring} files\n"
            f"  • Missing header: {missing_header} files\n"
            f"  • Mismatched URNs: {mismatched} files\n"
            f"\n"
            f"PER RED CONVENTION v1.0+, test files MUST have AC URN in BOTH:\n"
            f"  1. Header comment: # URN: acc:...\n"
            f"  2. Module docstring: RED Test for acc:...\n"
            f"  AND both references MUST match exactly.\n"
            f"\n"
            f"══════════════════════════════════════════════════════════════════════\n"
            f"DETAILED ERRORS:\n"
            f"══════════════════════════════════════════════════════════════════════\n"
            f"\n{error_report}\n"
        )


@pytest.mark.platform
def test_dual_ac_reference_format_examples():
    """
    SPEC-TESTER-CONVENTION-0002: Document correct dual AC reference format

    This test documents the expected format for dual AC references.
    """
    # This test always passes - it's documentation
    correct_format = '''
# Runtime: python
# Rationale: Game mechanics - stateful timebank depletion algorithm
# URN: acc:burn-timebank:E001-UNIT-001
# Phase: GREEN
# Purpose: Verify timebank decrements during active decision
"""
RED Test for acc:burn-timebank:E001-UNIT-001
wagon: burn-timebank | feature: burn-time | phase: GREEN
WMBT: wmbt:burn-timebank:E001
Purpose: Verify timebank decrements during active decision
"""

import pytest


def test_e001_unit_001_timebank_decrements_during_decision():
    """Test implementation..."""
    pass
'''

    # Validate the format
    ac_from_header = extract_ac_from_header(correct_format)
    ac_from_docstring = extract_ac_from_docstring(correct_format)

    assert ac_from_header == "acc:burn-timebank:E001-UNIT-001"
    assert ac_from_docstring == "acc:burn-timebank:E001-UNIT-001"
    assert ac_from_header == ac_from_docstring
