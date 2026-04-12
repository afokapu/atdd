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

import ast
import pytest
import re
from pathlib import Path
from typing import List, Tuple

from atdd.coach.utils.repo import find_repo_root


# Path constants
REPO_ROOT = find_repo_root()
PYTHON_DIR = REPO_ROOT / "python"


# Complexity thresholds
MAX_CYCLOMATIC_COMPLEXITY = 10
MAX_NESTING_DEPTH = 4
MAX_FUNCTION_LINES = 50
MAX_FUNCTION_PARAMS = 6
MAX_COGNITIVE_COMPLEXITY = 15


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


def calculate_cognitive_complexity(source: str) -> List[Tuple[str, int, int]]:
    """
    Calculate cognitive complexity for each function using the SonarQube
    algorithm (G. Ann Campbell, 2016).

    Structural increment (+1):
        if, elif, else, for, while, except, with, and, or

    Nesting increment (+N, where N = current nesting depth):
        Applied to if, for, while, except, with when nested inside
        another control-flow structure.  NOT applied to elif/else
        (they continue the chain) or boolean operators.

    Each function is analysed independently — nested function bodies
    do not contribute to the enclosing function's score.

    Returns:
        List of (function_name, line_number, complexity) tuples.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: List[Tuple[str, int, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = _function_cognitive_complexity(node)
            results.append((node.name, node.lineno, cc))

    return results


def _function_cognitive_complexity(func_node: ast.AST) -> int:
    """Compute cognitive complexity for a single function AST node."""
    state = {"complexity": 0}

    # -- expression walker: finds BoolOp sequences -------------------------
    def _walk_expr(expr: ast.AST) -> None:
        if isinstance(expr, ast.BoolOp):
            # One BoolOp node = one sequence of the same operator → +1
            state["complexity"] += 1
        for child in ast.iter_child_nodes(expr):
            _walk_expr(child)

    # -- statement walker ---------------------------------------------------
    def _walk_stmts(stmts, nesting: int) -> None:
        for stmt in stmts:
            _walk(stmt, nesting)

    def _handle_if_chain(node: ast.If, nesting: int) -> None:
        """Handle an if / elif / else chain."""
        # First 'if': +1 + nesting
        state["complexity"] += 1 + nesting
        _walk_expr(node.test)
        _walk_stmts(node.body, nesting + 1)

        orelse = node.orelse
        while orelse:
            if len(orelse) == 1 and isinstance(orelse[0], ast.If):
                # elif: +1, NO nesting penalty
                elif_node = orelse[0]
                state["complexity"] += 1
                _walk_expr(elif_node.test)
                _walk_stmts(elif_node.body, nesting + 1)
                orelse = elif_node.orelse
            else:
                # else: +1, NO nesting penalty
                state["complexity"] += 1
                _walk_stmts(orelse, nesting + 1)
                orelse = None

    def _walk(node: ast.AST, nesting: int) -> None:
        # Nested function/class — skip (analysed independently)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return

        if isinstance(node, ast.If):
            _handle_if_chain(node, nesting)
            return

        if isinstance(node, (ast.For, ast.AsyncFor)):
            state["complexity"] += 1 + nesting
            _walk_expr(node.iter)
            _walk_stmts(node.body, nesting + 1)
            if node.orelse:
                state["complexity"] += 1
                _walk_stmts(node.orelse, nesting + 1)
            return

        if isinstance(node, ast.While):
            state["complexity"] += 1 + nesting
            _walk_expr(node.test)
            _walk_stmts(node.body, nesting + 1)
            if node.orelse:
                state["complexity"] += 1
                _walk_stmts(node.orelse, nesting + 1)
            return

        if isinstance(node, ast.Try):
            _walk_stmts(node.body, nesting)
            for handler in node.handlers:
                state["complexity"] += 1 + nesting
                _walk_stmts(handler.body, nesting + 1)
            if node.orelse:
                _walk_stmts(node.orelse, nesting)
            if node.finalbody:
                _walk_stmts(node.finalbody, nesting)
            return

        # Python 3.11+ try/except*
        if hasattr(ast, "TryStar") and isinstance(node, ast.TryStar):
            _walk_stmts(node.body, nesting)
            for handler in node.handlers:
                state["complexity"] += 1 + nesting
                _walk_stmts(handler.body, nesting + 1)
            if node.orelse:
                _walk_stmts(node.orelse, nesting)
            if node.finalbody:
                _walk_stmts(node.finalbody, nesting)
            return

        if isinstance(node, (ast.With, ast.AsyncWith)):
            state["complexity"] += 1 + nesting
            _walk_stmts(node.body, nesting + 1)
            return

        # Generic: recurse into child statements and expressions
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                _walk(child, nesting)
            elif isinstance(child, ast.expr):
                _walk_expr(child)

    _walk_stmts(func_node.body, 0)
    return state["complexity"]


def scan_cognitive_complexity(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for cognitive complexity violations. Used by ratchet baseline."""
    python_dir = repo_root / "python"
    if not python_dir.exists():
        return 0, []
    files = []
    for py_file in python_dir.rglob("*.py"):
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            continue
        if '__pycache__' in str(py_file) or py_file.name == '__init__.py':
            continue
        files.append(py_file)
    violations = []
    for py_file in files:
        try:
            source = py_file.read_text(encoding='utf-8')
        except Exception:
            continue
        for func_name, line_num, cc in calculate_cognitive_complexity(source):
            if cc > MAX_COGNITIVE_COMPLEXITY:
                rel_path = py_file.relative_to(repo_root)
                violations.append(f"{rel_path}:{line_num} {func_name} cognitive_complexity={cc}")
    return len(violations), violations


def scan_cyclomatic_complexity(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for cyclomatic complexity violations. Used by ratchet baseline."""
    python_dir = repo_root / "python"
    if not python_dir.exists():
        return 0, []
    files = []
    for py_file in python_dir.rglob("*.py"):
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            continue
        if '__pycache__' in str(py_file) or py_file.name == '__init__.py':
            continue
        files.append(py_file)
    violations = []
    for py_file in files:
        for func_name, line_num, func_body in extract_functions(py_file):
            if count_function_lines(func_body) < 3:
                continue
            complexity = calculate_cyclomatic_complexity(func_body)
            if complexity > MAX_CYCLOMATIC_COMPLEXITY:
                rel_path = py_file.relative_to(repo_root)
                violations.append(f"{rel_path}:{line_num} {func_name} complexity={complexity}")
    return len(violations), violations


def scan_nesting_depth(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for nesting depth violations. Used by ratchet baseline."""
    python_dir = repo_root / "python"
    if not python_dir.exists():
        return 0, []
    files = []
    for py_file in python_dir.rglob("*.py"):
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            continue
        if '__pycache__' in str(py_file) or py_file.name == '__init__.py':
            continue
        files.append(py_file)
    violations = []
    for py_file in files:
        for func_name, line_num, func_body in extract_functions(py_file):
            depth = calculate_nesting_depth(func_body)
            if depth > MAX_NESTING_DEPTH:
                rel_path = py_file.relative_to(repo_root)
                violations.append(f"{rel_path}:{line_num} {func_name} depth={depth}")
    return len(violations), violations


def scan_function_length(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for function length violations. Used by ratchet baseline."""
    python_dir = repo_root / "python"
    if not python_dir.exists():
        return 0, []
    files = []
    for py_file in python_dir.rglob("*.py"):
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            continue
        if '__pycache__' in str(py_file) or py_file.name == '__init__.py':
            continue
        files.append(py_file)
    violations = []
    for py_file in files:
        for func_name, line_num, func_body in extract_functions(py_file):
            lines = count_function_lines(func_body)
            if lines > MAX_FUNCTION_LINES:
                rel_path = py_file.relative_to(repo_root)
                violations.append(f"{rel_path}:{line_num} {func_name} lines={lines}")
    return len(violations), violations


def scan_function_params(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for function parameter count violations. Used by ratchet baseline."""
    python_dir = repo_root / "python"
    if not python_dir.exists():
        return 0, []
    files = []
    for py_file in python_dir.rglob("*.py"):
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            continue
        if '__pycache__' in str(py_file) or py_file.name == '__init__.py':
            continue
        files.append(py_file)
    violations = []
    for py_file in files:
        for func_name, line_num, func_body in extract_functions(py_file):
            param_count = count_function_parameters(func_body)
            if param_count > MAX_FUNCTION_PARAMS:
                rel_path = py_file.relative_to(repo_root)
                violations.append(f"{rel_path}:{line_num} {func_name} params={param_count}")
    return len(violations), violations


@pytest.mark.coder
def test_cyclomatic_complexity_under_threshold(ratchet_baseline):
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
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_files = find_python_files()
    if not python_files:
        pytest.skip("No Python files found")

    count, violations = scan_cyclomatic_complexity(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="cyclomatic_complexity",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_nesting_depth_under_threshold(ratchet_baseline):
    """
    SPEC-CODER-COMPLEXITY-0002: Functions have acceptable nesting depth.

    Deep nesting makes code:
    - Hard to read
    - Hard to test
    - More error-prone

    Threshold: < 4 levels

    Given: All Python functions
    When: Calculating nesting depth
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_files = find_python_files()
    if not python_files:
        pytest.skip("No Python files found")

    count, violations = scan_nesting_depth(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="nesting_depth",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_function_length_under_threshold(ratchet_baseline):
    """
    SPEC-CODER-COMPLEXITY-0003: Functions are not too long.

    Long functions are:
    - Hard to understand
    - Hard to test
    - Likely doing too much (SRP violation)

    Threshold: < 50 lines of code

    Given: All Python functions
    When: Counting lines of code
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_files = find_python_files()
    if not python_files:
        pytest.skip("No Python files found")

    count, violations = scan_function_length(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="function_length",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_function_parameter_count_under_threshold(ratchet_baseline):
    """
    SPEC-CODER-COMPLEXITY-0004: Functions don't have too many parameters.

    Too many parameters indicate:
    - Function doing too much
    - Poor abstraction
    - Hard to call/test

    Threshold: < 6 parameters

    Given: All Python functions
    When: Counting parameters
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_files = find_python_files()
    if not python_files:
        pytest.skip("No Python files found")

    count, violations = scan_function_params(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="function_parameter_count",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_cognitive_complexity_under_threshold(ratchet_baseline):
    """
    SPEC-CODER-COGNITIVE-0001: Functions have acceptable cognitive complexity.

    Cognitive complexity (SonarQube / G. Ann Campbell algorithm) measures how
    difficult code is to *understand*, penalising deeply nested structures.
    Unlike cyclomatic complexity, it distinguishes flat if/elif chains
    (low complexity) from deeply nested if(if(if)) structures (high complexity).

    Algorithm:
        +1 structural increment for if, elif, else, for, while, except,
        with, and, or.
        +N nesting increment (N = current nesting depth) for if, for,
        while, except, with when nested inside another control-flow
        structure.  elif/else continue the chain without nesting penalty.

    Threshold: <= 15 per function (SonarQube default)

    Given: All Python source functions
    When: Calculating cognitive complexity via AST
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_files = find_python_files()
    if not python_files:
        pytest.skip("No Python files found")

    count, violations = scan_cognitive_complexity(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="cognitive_complexity",
        current_count=count,
        violations=violations,
    )
