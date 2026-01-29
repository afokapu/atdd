#!/usr/bin/env python3
"""
Simple script to remove consecutive duplicate lines in test files.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_DIR = REPO_ROOT / "python"


def remove_consecutive_duplicates(content: str) -> tuple[str, bool]:
    """
    Remove consecutive duplicate lines.

    Returns:
        (cleaned_content, was_changed)
    """
    lines = content.split('\n')
    if not lines:
        return content, False

    clean_lines = [lines[0]]  # Always keep first line
    was_changed = False

    for i in range(1, len(lines)):
        if lines[i] != lines[i-1]:
            clean_lines.append(lines[i])
        else:
            # Skip duplicate line
            was_changed = True

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
    """Remove consecutive duplicate lines in all test files."""
    test_files = find_test_files()

    if not test_files:
        print("No test files found")
        return

    print(f"Checking {len(test_files)} test files for consecutive duplicates")
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

        cleaned_content, was_changed = remove_consecutive_duplicates(original_content)

        if was_changed:
            try:
                with open(test_file, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                rel_path = test_file.relative_to(REPO_ROOT)
                print(f"✅ {rel_path}")
                print(f"   Removed consecutive duplicate lines")
                cleaned_count += 1
            except Exception as e:
                print(f"❌ {test_file.relative_to(REPO_ROOT)}")
                print(f"   ERROR: Could not write: {e}")

    print("=" * 80)
    print(f"Cleaned {cleaned_count} files")


if __name__ == "__main__":
    main()
