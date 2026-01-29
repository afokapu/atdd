#!/usr/bin/env python3
"""
Script to clean up duplicate header comments - Version 2.

This version removes ALL old header-style comments after the first URN,
keeping only the new standardized header at the top.
"""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_DIR = REPO_ROOT / "python"


def clean_file_content(content: str) -> tuple[str, bool]:
    """
    Clean up file by removing duplicate/old headers.

    Strategy:
    1. Find first URN line (this is our canonical header start)
    2. After canonical header block ends, remove any old URN/header lines
    3. Keep the module docstring and code

    Returns:
        (cleaned_content, was_changed)
    """
    lines = content.split('\n')

    # Find first URN line index
    first_urn_idx = None
    for i, line in enumerate(lines):
        if re.match(r'^#\s*URN:', line, re.IGNORECASE):
            first_urn_idx = i
            break

    if first_urn_idx is None:
        # No URN found, return as-is
        return content, False

    # Find end of first header block (after first URN)
    header_end_idx = first_urn_idx
    for i in range(first_urn_idx + 1, len(lines)):
        line = lines[i]
        # Continue while we see header comments or empty lines
        if line.startswith('#') or line.strip() == '':
            header_end_idx = i
        else:
            break

    # Now scan for and remove duplicate header lines after header_end_idx
    clean_lines = lines[:header_end_idx + 1]
    was_changed = False

    for i in range(header_end_idx + 1, len(lines)):
        line = lines[i]

        # Skip duplicate URN lines (any case)
        if re.match(r'^#\s*[uU][rR][nN]:', line):
            was_changed = True
            continue

        # Skip duplicate Runtime/Rationale lines after first header
        if re.match(r'^#\s*Runtime:', line):
            was_changed = True
            continue

        if re.match(r'^#\s*Rationale:', line):
            was_changed = True
            continue

        # Keep everything else
        clean_lines.append(line)

    cleaned = '\n'.join(clean_lines)
    return cleaned, was_changed


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
    """Clean up duplicate headers in all test files."""
    test_files = find_test_files()

    if not test_files:
        print("No test files found")
        return

    print(f"Checking {len(test_files)} test files for duplicate headers")
    print("=" * 80)

    cleaned_count = 0

    for test_file in sorted(test_files):
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                original_content = f.read()
        except Exception as e:
            print(f"❌ {test_file.relative_to(REPO_ROOT)}")
            print(f"   ERROR: Could not read: {e}")
            continue

        cleaned_content, was_changed = clean_file_content(original_content)

        if was_changed:
            try:
                with open(test_file, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                rel_path = test_file.relative_to(REPO_ROOT)
                print(f"✅ {rel_path}")
                print(f"   Removed duplicate header comments")
                cleaned_count += 1
            except Exception as e:
                print(f"❌ {test_file.relative_to(REPO_ROOT)}")
                print(f"   ERROR: Could not write: {e}")

    print("=" * 80)
    print(f"Cleaned {cleaned_count} files")


if __name__ == "__main__":
    main()
