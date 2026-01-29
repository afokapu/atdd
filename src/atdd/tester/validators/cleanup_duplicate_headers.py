#!/usr/bin/env python3
"""
Script to clean up duplicate header comments.

Some files have duplicate headers after the automated fix - this removes the old headers
and keeps only the new standardized ones.
"""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_DIR = REPO_ROOT / "python"


def clean_duplicate_headers(content: str) -> tuple[str, bool]:
    """
    Remove duplicate header comments, keeping only the first URN header.

    Returns:
        (cleaned_content, was_changed)
    """
    lines = content.split('\n')
    new_lines = []
    found_first_urn = False
    skip_mode = False
    skip_count = 0

    for i, line in enumerate(lines):
        # Check if this is a URN header
        if re.match(r'^#\s*URN:', line, re.IGNORECASE):
            if not found_first_urn:
                # This is the first URN header - keep it
                found_first_urn = True
                new_lines.append(line)
            else:
                # This is a duplicate URN header - start skipping
                skip_mode = True
                skip_count = 1  # Skip this line
                continue

        # If in skip mode, skip header-like lines after duplicate URN
        if skip_mode:
            # Check if this looks like a header comment
            if line.startswith('#') and not line.strip().startswith('# urn:'):
                skip_count += 1
                continue
            else:
                # End of duplicate header block
                skip_mode = False

        new_lines.append(line)

    cleaned = '\n'.join(new_lines)
    was_changed = skip_count > 0

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

        cleaned_content, was_changed = clean_duplicate_headers(original_content)

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
