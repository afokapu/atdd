"""
Test Python code complexity stays within acceptable thresholds.

Validates:
- Cyclomatic complexity < 10 per function
- Nesting depth < 4 levels
- Function length < 50 lines
- No overly complex functions

Inspired by: .claude/utils/coder/complexity.py
But: Self-contained, no utility dependencies
"""

import pytest
import re
from pathlib import Path
from typing import List, Tuple


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "python"


# Complexity thresholds
MAX_CYCLOMATIC_COMPLEXITY = 10
MAX_NESTING_DEPTH = 4
MAX_FUNCTION_LINES = 50
MAX_FUNCTION_PARAMS = 6


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
        if py_file.name == '__init__.py':
            continue
        files.append(py_file)

    return files


def extract_functions(file_path: Path) -> List[Tuple[str, int, str]]:
    """
    Extract functions from Python file.

    Returns:
        List of (function_name, line_number, function_body) tuples
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    functions = []
    lines = content.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i]

        # Match function definition: def function_name(...)
        func_match = re.match(r'^\s*(async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', line)

        if func_match:
            func_name = func_match.group(2)
            start_line = i + 1  # Line numbers are 1-based
            indent = len(line) - len(line.lstrip())

            # Extract function body
            body_lines = [line]
            i += 1

            # Find end of function (next line with same or less indentation that's not blank)
            while i < len(lines):
                current_line = lines[i]

                # Skip blank lines and comments
                if not current_line.strip() or current_line.strip().startswith('#'):
                    body_lines.append(current_line)
                    i += 1
                    continue

                current_indent = len(current_line) - len(current_line.lstrip())

                # If indentation is same or less and not blank, function ended
                if current_indent <= indent and current_line.strip():
                    break

                body_lines.append(current_line)
                i += 1

            function_body = '\n'.join(body_lines)
            functions.append((func_name, start_line, function_body))
        else:
            i += 1

    return functions


def calculate_cyclomatic_complexity(function_body: str) -> int:
    """
    Calculate cyclomatic complexity of a function.

    Cyclomatic complexity = number of decision points + 1

    Decision points:
    - if, elif
    - for, while
    - and, or (in conditions)
    - except
    - case (match statement)
    """
    complexity = 1  # Base complexity

    # Count decision keywords
    keywords = ['if', 'elif', 'for', 'while', 'except', 'case']
    for keyword in keywords:
        # Match keyword as whole word
        pattern = r'\b' + keyword + r'\b'
        complexity += len(re.findall(pattern, function_body))

    # Count boolean operators in conditions
    # (simplified - count 'and' and 'or' in lines with 'if', 'elif', 'while')
    condition_lines = [line for line in function_body.split('\n')
                      if re.search(r'\b(if|elif|while)\b', line)]

    for line in condition_lines:
        complexity += len(re.findall(r'\band\b', line))
        complexity += len(re.findall(r'\bor\b', line))

    return complexity


def calculate_nesting_depth(function_body: str) -> int:
    """
    Calculate maximum nesting depth in a function.

    Counts nested blocks (if, for, while, with, try, etc.)
    """
    max_depth = 0
    current_depth = 0
    base_indent = None

    for line in function_body.split('\n'):
        stripped = line.strip()

        # Skip blank lines and comments
        if not stripped or stripped.startswith('#'):
            continue

        # Calculate indentation
        indent = len(line) - len(line.lstrip())

        # Set base indent from first non-empty line
        if base_indent is None:
            base_indent = indent
            continue

        # Calculate depth relative to function start
        relative_indent = indent - base_indent

        # Each 4 spaces = 1 level (standard Python indentation)
        current_depth = relative_indent // 4

        # Check if line introduces a new block
        if stripped.endswith(':') and any(
            stripped.startswith(kw) for kw in
            ['if', 'elif', 'else', 'for', 'while', 'with', 'try', 'except', 'finally', 'def', 'class']
        ):
            max_depth = max(max_depth, current_depth + 1)
        else:
            max_depth = max(max_depth, current_depth)

    return max_depth


def count_function_lines(function_body: str) -> int:
    """
    Count lines of code in function (excluding blank lines and comments).
    """
    lines = function_body.split('\n')
    code_lines = 0

    for line in lines:
        stripped = line.strip()
        # Skip blank lines and pure comment lines
        if stripped and not stripped.startswith('#'):
            code_lines += 1

    return code_lines


def count_function_parameters(function_body: str) -> int:
    """
    Count number of parameters in function definition.
    """
    # Extract first line (function signature)
    first_line = function_body.split('\n')[0]

    # Extract parameters from signature
    match = re.search(r'def\s+\w+\s*\((.*?)\)', first_line)
    if not match:
        return 0

    params = match.group(1).strip()

    # No parameters
    if not params:
        return 0

    # Split by comma (simple counting)
    # This is simplified - doesn't handle complex default values perfectly
    param_list = [p.strip() for p in params.split(',')]

    # Filter out 'self' and 'cls'
    param_list = [p for p in param_list if not p.startswith('self') and not p.startswith('cls')]

    return len(param_list)


@pytest.mark.coder
def test_cyclomatic_complexity_under_threshold():
    """
    SPEC-CODER-COMPLEXITY-0001: Functions have acceptable cyclomatic complexity.

    Cyclomatic complexity measures the number of independent paths through code.
    High complexity indicates code that is:
    - Hard to test
    - Hard to understand
    - More likely to contain bugs

    Threshold: < 10 (industry standard)

    Given: All Python functions
    When: Calculating cyclomatic complexity
    Then: Complexity < 10 for all functions
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    violations = []

    for py_file in python_files:
        functions = extract_functions(py_file)

        for func_name, line_num, func_body in functions:
            # Skip very small functions (< 3 lines)
            if count_function_lines(func_body) < 3:
                continue

            complexity = calculate_cyclomatic_complexity(func_body)

            if complexity > MAX_CYCLOMATIC_COMPLEXITY:
                rel_path = py_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{line_num}\\n"
                    f"  Function: {func_name}\\n"
                    f"  Complexity: {complexity} (max: {MAX_CYCLOMATIC_COMPLEXITY})\\n"
                    f"  Suggestion: Break into smaller functions"
                )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} complexity violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.coder
def test_nesting_depth_under_threshold():
    """
    SPEC-CODER-COMPLEXITY-0002: Functions have acceptable nesting depth.

    Deep nesting makes code:
    - Hard to read
    - Hard to test
    - More error-prone

    Threshold: < 4 levels

    Given: All Python functions
    When: Calculating nesting depth
    Then: Depth < 4 for all functions
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    violations = []

    for py_file in python_files:
        functions = extract_functions(py_file)

        for func_name, line_num, func_body in functions:
            depth = calculate_nesting_depth(func_body)

            if depth > MAX_NESTING_DEPTH:
                rel_path = py_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{line_num}\\n"
                    f"  Function: {func_name}\\n"
                    f"  Nesting depth: {depth} (max: {MAX_NESTING_DEPTH})\\n"
                    f"  Suggestion: Extract nested logic into separate functions"
                )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} nesting depth violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.coder
def test_function_length_under_threshold():
    """
    SPEC-CODER-COMPLEXITY-0003: Functions are not too long.

    Long functions are:
    - Hard to understand
    - Hard to test
    - Likely doing too much (SRP violation)

    Threshold: < 50 lines of code

    Given: All Python functions
    When: Counting lines of code
    Then: Length < 50 for all functions
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    violations = []

    for py_file in python_files:
        functions = extract_functions(py_file)

        for func_name, line_num, func_body in functions:
            lines = count_function_lines(func_body)

            if lines > MAX_FUNCTION_LINES:
                rel_path = py_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{line_num}\\n"
                    f"  Function: {func_name}\\n"
                    f"  Lines: {lines} (max: {MAX_FUNCTION_LINES})\\n"
                    f"  Suggestion: Break into smaller functions"
                )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} function length violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.coder
def test_function_parameter_count_under_threshold():
    """
    SPEC-CODER-COMPLEXITY-0004: Functions don't have too many parameters.

    Too many parameters indicate:
    - Function doing too much
    - Poor abstraction
    - Hard to call/test

    Threshold: < 6 parameters

    Given: All Python functions
    When: Counting parameters
    Then: Parameters < 6 for all functions
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    violations = []

    for py_file in python_files:
        functions = extract_functions(py_file)

        for func_name, line_num, func_body in functions:
            param_count = count_function_parameters(func_body)

            if param_count > MAX_FUNCTION_PARAMS:
                rel_path = py_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{line_num}\\n"
                    f"  Function: {func_name}\\n"
                    f"  Parameters: {param_count} (max: {MAX_FUNCTION_PARAMS})\\n"
                    f"  Suggestion: Use parameter objects or reduce responsibilities"
                )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} parameter count violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )
