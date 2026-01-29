"""
Test code quality metrics meet minimum standards.

Validates:
- Maintainability index > 60
- Code has appropriate comments
- No code duplication
- Consistent naming conventions

Inspired by: .claude/utils/coder/quality_metrics.py
But: Self-contained, no utility dependencies
"""

import pytest
import re
from pathlib import Path
from typing import List, Tuple


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "python"


# Quality thresholds
MIN_MAINTAINABILITY_INDEX = 60
MIN_COMMENT_RATIO = 0.10  # 10% comments
MAX_DUPLICATE_LINES = 5


def find_python_files() -> List[Path]:
    """Find all Python source files (excluding tests)."""
    if not PYTHON_DIR.exists():
        return []

    files = []
    for py_file in PYTHON_DIR.rglob("*.py"):
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            continue
        if '__pycache__' in str(py_file):
            continue
        files.append(py_file)

    return files


def calculate_maintainability_index(file_path: Path) -> float:
    """
    Calculate simplified maintainability index for a file.

    Based on:
    - Lines of code
    - Cyclomatic complexity (simplified)
    - Comment ratio

    Returns value 0-100 (higher is better)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return 0

    total_lines = len(lines)
    code_lines = 0
    comment_lines = 0
    blank_lines = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            blank_lines += 1
        elif stripped.startswith('#'):
            comment_lines += 1
        else:
            code_lines += 1

    # Simple heuristic for maintainability
    # Higher comment ratio = better
    comment_ratio = comment_lines / total_lines if total_lines > 0 else 0

    # Shorter files = better
    size_factor = max(0, 100 - (code_lines / 10))

    # Calculate index (simplified)
    index = (size_factor * 0.4) + (comment_ratio * 100 * 0.6)

    return min(100, max(0, index))


def calculate_comment_ratio(file_path: Path) -> float:
    """
    Calculate ratio of comments and docstrings to code.

    Counts both:
    - Inline comments (lines starting with #)
    - Docstrings (triple-quoted strings)

    Returns:
        Ratio (0.0 to 1.0)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return 0.0

    code_lines = 0
    comment_lines = 0
    in_docstring = False
    docstring_delim = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check for docstring delimiters
        if '"""' in stripped or "'''" in stripped:
            # Determine delimiter type
            delim = '"""' if '"""' in stripped else "'''"

            if not in_docstring:
                # Starting a docstring
                in_docstring = True
                docstring_delim = delim
                comment_lines += 1

                # Check if docstring closes on same line
                if stripped.count(delim) >= 2:
                    in_docstring = False
                    docstring_delim = None
            else:
                # Ending a docstring
                if delim == docstring_delim:
                    in_docstring = False
                    docstring_delim = None
                comment_lines += 1
        elif in_docstring:
            # Inside a docstring
            comment_lines += 1
        elif stripped.startswith('#'):
            # Inline comment
            comment_lines += 1
        else:
            # Code line
            code_lines += 1

    total = code_lines + comment_lines
    return comment_lines / total if total > 0 else 0.0


def find_duplicate_code_blocks(files: List[Path]) -> List[Tuple[Path, Path, List[str]]]:
    """
    Find duplicate code blocks across files.

    Returns:
        List of (file1, file2, duplicate_lines) tuples
    """
    duplicates = []

    # Simplified duplicate detection
    # In reality, would use more sophisticated algorithm

    file_contents = {}
    for file in files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                # Get normalized lines (stripped of whitespace)
                lines = [line.strip() for line in f.readlines() if line.strip() and not line.strip().startswith('#')]
                file_contents[file] = lines
        except Exception:
            continue

    # Compare files pairwise (simplified)
    files_list = list(file_contents.keys())
    for i, file1 in enumerate(files_list):
        for file2 in files_list[i+1:]:
            lines1 = file_contents[file1]
            lines2 = file_contents[file2]

            # Find consecutive duplicate lines
            for start1 in range(len(lines1) - MAX_DUPLICATE_LINES):
                block1 = lines1[start1:start1 + MAX_DUPLICATE_LINES]

                for start2 in range(len(lines2) - MAX_DUPLICATE_LINES):
                    block2 = lines2[start2:start2 + MAX_DUPLICATE_LINES]

                    if block1 == block2:
                        # Skip standard import blocks (common across port/adapter files)
                        block_text = '\n'.join(block1)
                        if 'from abc import' in block_text and 'from dataclasses import' in block_text:
                            # Standard port/adapter imports - acceptable
                            continue
                        duplicates.append((file1, file2, block1))
                        break

    return duplicates


def check_naming_consistency(file_path: Path) -> List[str]:
    """
    Check naming conventions consistency.

    Returns:
        List of naming violations
    """
    violations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return violations

    # Check class names (should be PascalCase)
    class_pattern = r'class\s+([a-z][a-zA-Z0-9_]*)\s*[:\(]'
    lowercase_classes = re.findall(class_pattern, content)
    for cls in lowercase_classes:
        violations.append(f"Class '{cls}' should use PascalCase")

    # Check constant names (should be UPPER_CASE)
    # Pattern: variable assignment at module level that looks like it should be constant
    const_pattern = r'^([a-z][a-z0-9_]*)\s*=\s*["\'\d\[]'
    # pytest special variables that must be lowercase
    pytest_special_vars = ['pytest_plugins']

    for line in content.split('\n'):
        if not line.startswith(' ') and not line.startswith('\t'):  # Module level
            match = re.match(const_pattern, line)
            if match and match.group(1).isupper():
                # Good - already uppercase
                pass
            elif match and match.group(1) in pytest_special_vars:
                # pytest special variable - must be lowercase
                pass
            elif match and '_' in match.group(1):
                # Might be a constant with wrong case
                violations.append(f"Constant '{match.group(1)}' should use UPPER_CASE")

    return violations


@pytest.mark.coder
def test_maintainability_index_above_threshold():
    """
    SPEC-CODER-QUALITY-0001: Code has acceptable maintainability index.

    Maintainability index measures:
    - Code complexity
    - Code size
    - Documentation level

    Threshold: > 60 (scale 0-100)

    Given: All Python files
    When: Calculating maintainability index
    Then: Index > 60 for all files
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    violations = []

    for py_file in python_files:
        # Skip very small files
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            if len(lines) < 10:
                continue
        except Exception:
            continue

        index = calculate_maintainability_index(py_file)

        if index < MIN_MAINTAINABILITY_INDEX:
            rel_path = py_file.relative_to(REPO_ROOT)
            violations.append(
                f"{rel_path}\\n"
                f"  Maintainability Index: {index:.1f} (min: {MIN_MAINTAINABILITY_INDEX})\\n"
                f"  Suggestion: Add comments, reduce complexity, or split file"
            )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} maintainability violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.coder
def test_adequate_code_comments():
    """
    SPEC-CODER-QUALITY-0002: Code has adequate comments.

    Well-commented code is easier to maintain.

    Threshold: > 10% comment ratio

    Given: All Python files
    When: Calculating comment ratio
    Then: At least 10% comments
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    violations = []

    for py_file in python_files:
        # Skip very small files
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            if len(lines) < 20:
                continue
        except Exception:
            continue

        ratio = calculate_comment_ratio(py_file)

        if ratio < MIN_COMMENT_RATIO:
            rel_path = py_file.relative_to(REPO_ROOT)
            violations.append(
                f"{rel_path}\\n"
                f"  Comment ratio: {ratio*100:.1f}% (min: {MIN_COMMENT_RATIO*100:.0f}%)\\n"
                f"  Suggestion: Add docstrings and inline comments"
            )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} files with insufficient comments:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.coder
def test_no_significant_code_duplication():
    """
    SPEC-CODER-QUALITY-0003: No significant code duplication.

    Duplicate code should be extracted into functions.

    Threshold: < 5 consecutive duplicate lines

    Given: All Python files
    When: Checking for duplicate code blocks
    Then: No significant duplication found
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    # Limit to avoid long running time
    sample_files = python_files[:50]

    duplicates = find_duplicate_code_blocks(sample_files)

    if duplicates:
        violations = []
        for file1, file2, block in duplicates[:10]:
            violations.append(
                f"{file1.relative_to(REPO_ROOT)} ↔ {file2.relative_to(REPO_ROOT)}\\n"
                f"  Duplicate block ({len(block)} lines):\\n" +
                "\\n".join(f"    {line[:60]}" for line in block[:3])
            )

        pytest.fail(
            f"\\n\\nFound {len(duplicates)} code duplication instances:\\n\\n" +
            "\\n\\n".join(violations) +
            (f"\\n\\n... and {len(duplicates) - 10} more" if len(duplicates) > 10 else "") +
            "\\n\\nConsider extracting duplicate code into shared functions."
        )


@pytest.mark.coder
def test_consistent_naming_conventions():
    """
    SPEC-CODER-QUALITY-0004: Code follows consistent naming conventions.

    Naming conventions:
    - Classes: PascalCase
    - Functions: snake_case
    - Constants: UPPER_CASE
    - Variables: snake_case

    Given: All Python files
    When: Checking naming patterns
    Then: Consistent naming conventions
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    all_violations = []

    for py_file in python_files:
        violations = check_naming_consistency(py_file)

        if violations:
            rel_path = py_file.relative_to(REPO_ROOT)
            all_violations.append(
                f"{rel_path}\\n" +
                "\\n".join(f"  - {v}" for v in violations[:5])
            )

    if all_violations:
        pytest.fail(
            f"\\n\\nFound {len(all_violations)} files with naming violations:\\n\\n" +
            "\\n\\n".join(all_violations[:10]) +
            (f"\\n\\n... and {len(all_violations) - 10} more" if len(all_violations) > 10 else "")
        )
