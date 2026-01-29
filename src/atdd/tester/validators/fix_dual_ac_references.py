#!/usr/bin/env python3
"""
Script to automatically fix dual AC reference violations.

Fixes:
1. Missing header comments (adds # URN: acc:... at top)
2. Missing module docstrings (adds RED Test for acc:... after headers)
"""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_DIR = REPO_ROOT / "python"


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


def add_header_comment(content: str, ac_urn: str) -> str:
    """Add header comment with AC URN at the top of the file."""
    header = f"""# Runtime: python
# Rationale: Test implementation for acceptance criteria
# URN: {ac_urn}
# Phase: RED
# Purpose: Verify acceptance criteria

"""
    return header + content


def add_module_docstring(content: str, ac_urn: str) -> str:
    """Add module docstring with AC URN after header comments."""
    # Find the end of header comments
    lines = content.split('\n')
    insert_index = 0

    # Skip header comments
    for i, line in enumerate(lines):
        if line.startswith('#') or line.strip() == '':
            insert_index = i + 1
        else:
            break

    # Create docstring
    docstring = f'''"""
RED Test for {ac_urn}
wagon: {{wagon}} | feature: {{feature}} | phase: RED
WMBT: {{wmbt URN}}
Purpose: {{acceptance criteria purpose}}
"""

'''

    # Insert docstring
    lines.insert(insert_index, docstring.rstrip())
    return '\n'.join(lines)


def fix_file(file_path: Path) -> tuple[bool, str]:
    """
    Fix a single file.

    Returns:
        (changed, message) tuple
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        return False, f"ERROR: Could not read: {e}"

    ac_from_header = extract_ac_from_header(original_content)
    ac_from_docstring = extract_ac_from_docstring(original_content)

    # Skip if both are present
    if ac_from_header and ac_from_docstring:
        return False, "SKIP: Already has both header and docstring"

    # Skip if neither is present (legacy test)
    if not ac_from_header and not ac_from_docstring:
        return False, "SKIP: Legacy test without AC URN"

    new_content = original_content
    changes = []

    # Add missing header
    if ac_from_docstring and not ac_from_header:
        new_content = add_header_comment(new_content, ac_from_docstring)
        changes.append("Added header comment")

    # Add missing docstring
    if ac_from_header and not ac_from_docstring:
        new_content = add_module_docstring(new_content, ac_from_header)
        changes.append("Added module docstring")

    # Write back
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True, f"FIXED: {', '.join(changes)}"
    except Exception as e:
        return False, f"ERROR: Could not write: {e}"


def find_test_files() -> list:
    """Find all Python test files."""
    if not PYTHON_DIR.exists():
        return []

    test_files = []
    for py_file in PYTHON_DIR.rglob("test_*.py"):
        if '__pycache__' in str(py_file) or 'conftest' in py_file.name:
            continue
        test_files.append(py_file)

    return test_files


def main():
    """Fix all test files with dual AC reference violations."""
    test_files = find_test_files()

    if not test_files:
        print("No test files found")
        return

    print(f"Found {len(test_files)} test files")
    print("=" * 80)

    fixed_count = 0
    skipped_count = 0
    error_count = 0

    for test_file in sorted(test_files):
        rel_path = test_file.relative_to(REPO_ROOT)
        changed, message = fix_file(test_file)

        if changed:
            print(f"✅ {rel_path}")
            print(f"   {message}")
            fixed_count += 1
        elif "ERROR" in message:
            print(f"❌ {rel_path}")
            print(f"   {message}")
            error_count += 1
        else:
            # Skip printing for files that don't need changes
            skipped_count += 1

    print("=" * 80)
    print(f"Summary:")
    print(f"  Fixed: {fixed_count} files")
    print(f"  Skipped: {skipped_count} files")
    print(f"  Errors: {error_count} files")
    print()
    print(f"Total processed: {len(test_files)} files")


if __name__ == "__main__":
    main()
