"""
Test TypeScript/TSX code complexity stays within acceptable thresholds.

Validates:
- Cyclomatic complexity <= 10 per function
- Nesting depth <= 4 levels
- Function length <= 50 lines

Regex-based — no AST parser or tree-sitter dependency.
Same thresholds as the Python counterpart (test_complexity.py).
Uses ratchet baseline to prevent regression.

Convention: src/atdd/coder/conventions/quality.convention.yaml
"""

import re
import pytest
from pathlib import Path
from typing import List, Tuple

from atdd.coach.utils.repo import find_repo_root


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
WEB_SRC = REPO_ROOT / "web" / "src"

# ---------------------------------------------------------------------------
# Complexity thresholds (parity with test_complexity.py)
# ---------------------------------------------------------------------------
MAX_CYCLOMATIC_COMPLEXITY = 10
MAX_NESTING_DEPTH = 4
MAX_FUNCTION_LINES = 50

_SKIP_DIRS = {
    "node_modules", "dist", "build", ".next", ".nuxt",
    "coverage", ".cache", "__tests__", "__mocks__",
}

_TS_EXTENSIONS = {".ts", ".tsx"}


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def find_typescript_files(root: Path | None = None) -> List[Path]:
    """Find all TypeScript source files under web/src (excluding tests)."""
    src = root or WEB_SRC
    if not src.exists():
        return []

    files: List[Path] = []
    for ts_file in src.rglob("*"):
        if ts_file.suffix not in _TS_EXTENSIONS:
            continue
        parts = ts_file.parts
        if any(d in _SKIP_DIRS for d in parts):
            continue
        # Skip test files
        if ".test." in ts_file.name or ".spec." in ts_file.name:
            continue
        if ts_file.name.startswith("test_") or "/tests/" in str(ts_file):
            continue
        files.append(ts_file)

    return files


# ---------------------------------------------------------------------------
# Function extraction (regex-based)
# ---------------------------------------------------------------------------

# Patterns that capture TS/TSX function definitions:
#   function name(...)          — named function declaration
#   const name = (...)  =>      — arrow function assigned to const
#   const name = function(...)  — function expression
#   export function name(...)   — exported function
#   async function name(...)    — async variants
#   name(...)  { (method)       — class method (indented)
_FUNC_PATTERNS = [
    # function declarations (with optional export/async)
    re.compile(
        r"^(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*"
        r"(?:<[^>]*>)?"  # optional generic
        r"\s*\(",
        re.MULTILINE,
    ),
    # arrow / function expression: const name = (...) => or const name = function(
    re.compile(
        r"^(?:export\s+)?(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*"
        r"(?::\s*[^=]+?)?"  # optional type annotation
        r"\s*=\s*(?:async\s+)?(?:function\s*)?(?:<[^>]*>)?\s*\(",
        re.MULTILINE,
    ),
]


def extract_functions_ts(file_path: Path) -> List[Tuple[str, int, str]]:
    """
    Extract functions from a TypeScript file using regex + brace matching.

    Returns:
        List of (function_name, line_number, function_body) tuples
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []

    lines = content.split("\n")
    functions: List[Tuple[str, int, str]] = []

    for pattern in _FUNC_PATTERNS:
        for match in pattern.finditer(content):
            func_name = match.group(1)
            # Calculate line number (1-based)
            line_num = content[: match.start()].count("\n") + 1

            # Find the opening brace of the function body
            body_start = _find_opening_brace(content, match.end())
            if body_start == -1:
                # Arrow function without braces (expression body) — single line
                # Extract to end of statement
                stmt_end = content.find("\n", match.end())
                if stmt_end == -1:
                    stmt_end = len(content)
                body = content[match.start() : stmt_end]
                functions.append((func_name, line_num, body))
                continue

            # Match braces to find function end
            body_end = _match_braces(content, body_start)
            if body_end == -1:
                continue

            body = content[match.start() : body_end + 1]
            functions.append((func_name, line_num, body))

    return functions


def _find_opening_brace(content: str, start: int) -> int:
    """Find the first '{' after start, skipping parens and arrow."""
    i = start
    paren_depth = 0
    while i < len(content):
        ch = content[i]
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
        elif ch == "{" and paren_depth == 0:
            return i
        elif ch == "\n" and paren_depth == 0:
            # Check if this is an expression arrow (no braces)
            # Look back for =>
            segment = content[start:i]
            if "=>" in segment and "{" not in segment:
                return -1
        i += 1
    return -1


def _match_braces(content: str, open_pos: int) -> int:
    """Find the matching closing brace for the one at open_pos."""
    depth = 0
    i = open_pos
    in_string = None
    in_template = 0
    in_line_comment = False
    in_block_comment = False

    while i < len(content):
        ch = content[i]

        # Line comment
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        # Block comment
        if in_block_comment:
            if ch == "*" and i + 1 < len(content) and content[i + 1] == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        # String handling
        if in_string:
            if ch == "\\" and i + 1 < len(content):
                i += 2  # skip escaped char
                continue
            if in_string == "`":
                if ch == "$" and i + 1 < len(content) and content[i + 1] == "{":
                    in_template += 1
                    i += 2
                    continue
                if ch == "}" and in_template > 0:
                    in_template -= 1
                    i += 1
                    continue
            if ch == in_string and in_template == 0:
                in_string = None
            i += 1
            continue

        # Comment start
        if ch == "/" and i + 1 < len(content):
            if content[i + 1] == "/":
                in_line_comment = True
                i += 2
                continue
            if content[i + 1] == "*":
                in_block_comment = True
                i += 2
                continue

        # String start
        if ch in ("'", '"', "`"):
            in_string = ch
            i += 1
            continue

        # Brace matching
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i

        i += 1

    return -1


# ---------------------------------------------------------------------------
# Cyclomatic complexity (regex-based)
# ---------------------------------------------------------------------------
def calculate_cyclomatic_complexity_ts(function_body: str) -> int:
    """
    Calculate cyclomatic complexity for a TypeScript function body.

    Decision points:
    - if, else if
    - for, while, do
    - case (switch)
    - catch
    - && , || (in conditions)
    - ?? (nullish coalescing)
    - ?. used in ternary-like patterns
    """
    complexity = 1  # base path

    # Decision keywords
    keywords = ["if", "else\\s+if", "for", "while", "do", "catch", "case"]
    for kw in keywords:
        pattern = r"\b" + kw + r"\b"
        complexity += len(re.findall(pattern, function_body))

    # Boolean operators (&&, ||) — each adds a branch
    complexity += len(re.findall(r"&&", function_body))
    complexity += len(re.findall(r"\|\|", function_body))

    # Nullish coalescing (??) — adds a branch
    complexity += len(re.findall(r"\?\?", function_body))

    # Ternary operator (? :) — rough count via standalone ?
    # Only count ? that is preceded by non-whitespace and followed by non-. (not ?.)
    complexity += len(re.findall(r"[^\s?]\s*\?(?![\s.?:])\s*[^:]", function_body))

    return complexity


# ---------------------------------------------------------------------------
# Nesting depth (brace / indent based)
# ---------------------------------------------------------------------------
def calculate_nesting_depth_ts(function_body: str) -> int:
    """
    Calculate maximum nesting depth inside a TypeScript function body.

    Tracks brace depth, counting only braces that follow control-flow keywords.
    """
    max_depth = 0
    control_depth = 0
    lines = function_body.split("\n")

    # Track brace depth per line, increment control_depth only when a
    # control-flow keyword precedes the opening brace on the same line
    _CONTROL_KW = re.compile(
        r"\b(if|else|for|while|do|switch|try|catch|finally)\b"
    )

    brace_depth = 0
    base_depth = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
            continue

        # Count braces on this line (outside strings — simplified)
        opens = stripped.count("{")
        closes = stripped.count("}")

        if base_depth is None and opens > 0:
            base_depth = brace_depth

        prev_depth = brace_depth

        # Check if this line has a control-flow keyword before the brace
        has_control = bool(_CONTROL_KW.search(stripped))

        brace_depth += opens - closes

        if has_control and opens > 0:
            control_depth = brace_depth - (base_depth or 0)
            max_depth = max(max_depth, control_depth)
        elif opens > 0:
            # Non-control brace (object literal, arrow body, etc.) — don't
            # count toward nesting, but track for depth calculation
            pass

        # When closing braces bring us below a tracked depth
        if closes > 0 and brace_depth < prev_depth:
            control_depth = max(0, brace_depth - (base_depth or 0))

    return max_depth


# ---------------------------------------------------------------------------
# Function length
# ---------------------------------------------------------------------------
def count_function_lines_ts(function_body: str) -> int:
    """Count lines of code (excluding blank lines and comment-only lines)."""
    count = 0
    in_block_comment = False

    for line in function_body.split("\n"):
        stripped = line.strip()

        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue

        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
            continue

        if not stripped:
            continue
        if stripped.startswith("//"):
            continue

        count += 1

    return count


# ---------------------------------------------------------------------------
# Scan functions (used by ratchet baseline registration)
# ---------------------------------------------------------------------------
def scan_cyclomatic_complexity_ts(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for cyclomatic complexity violations in TS/TSX files."""
    web_src = repo_root / "web" / "src"
    if not web_src.exists():
        return 0, []

    files = find_typescript_files(web_src)
    violations: List[str] = []

    for ts_file in files:
        for func_name, line_num, func_body in extract_functions_ts(ts_file):
            if count_function_lines_ts(func_body) < 3:
                continue
            complexity = calculate_cyclomatic_complexity_ts(func_body)
            if complexity > MAX_CYCLOMATIC_COMPLEXITY:
                rel_path = ts_file.relative_to(repo_root)
                violations.append(
                    f"{rel_path}:{line_num} {func_name} complexity={complexity}"
                )

    return len(violations), violations


def scan_nesting_depth_ts(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for nesting depth violations in TS/TSX files."""
    web_src = repo_root / "web" / "src"
    if not web_src.exists():
        return 0, []

    files = find_typescript_files(web_src)
    violations: List[str] = []

    for ts_file in files:
        for func_name, line_num, func_body in extract_functions_ts(ts_file):
            depth = calculate_nesting_depth_ts(func_body)
            if depth > MAX_NESTING_DEPTH:
                rel_path = ts_file.relative_to(repo_root)
                violations.append(
                    f"{rel_path}:{line_num} {func_name} depth={depth}"
                )

    return len(violations), violations


def scan_function_length_ts(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for function length violations in TS/TSX files."""
    web_src = repo_root / "web" / "src"
    if not web_src.exists():
        return 0, []

    files = find_typescript_files(web_src)
    violations: List[str] = []

    for ts_file in files:
        for func_name, line_num, func_body in extract_functions_ts(ts_file):
            lines = count_function_lines_ts(func_body)
            if lines > MAX_FUNCTION_LINES:
                rel_path = ts_file.relative_to(repo_root)
                violations.append(
                    f"{rel_path}:{line_num} {func_name} lines={lines}"
                )

    return len(violations), violations


# ---------------------------------------------------------------------------
# Pytest tests
# ---------------------------------------------------------------------------
@pytest.mark.coder
def test_cyclomatic_complexity_typescript(ratchet_baseline):
    """
    SPEC-CODER-COMPLEXITY-TS-0001: TS functions have acceptable cyclomatic complexity.

    Cyclomatic complexity measures the number of independent paths through code.
    Regex-based analysis — no AST parser dependency.

    Threshold: <= 10 (industry standard, parity with Python validator)

    Given: All TypeScript/TSX source functions under web/src
    When: Calculating cyclomatic complexity via regex pattern matching
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    ts_files = find_typescript_files()
    if not ts_files:
        pytest.skip("No TypeScript files found under web/src")

    count, violations = scan_cyclomatic_complexity_ts(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="cyclomatic_complexity_typescript",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_nesting_depth_typescript(ratchet_baseline):
    """
    SPEC-CODER-COMPLEXITY-TS-0002: TS functions have acceptable nesting depth.

    Deep nesting in TypeScript (nested if/for/switch blocks) makes code
    hard to read and test. Regex-based brace tracking.

    Threshold: <= 4 levels (parity with Python validator)

    Given: All TypeScript/TSX source functions under web/src
    When: Calculating nesting depth via brace tracking
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    ts_files = find_typescript_files()
    if not ts_files:
        pytest.skip("No TypeScript files found under web/src")

    count, violations = scan_nesting_depth_ts(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="nesting_depth_typescript",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_function_length_typescript(ratchet_baseline):
    """
    SPEC-CODER-COMPLEXITY-TS-0003: TS functions are not too long.

    Long functions violate SRP and are hard to test.
    Counts lines of code excluding blanks and comments.

    Threshold: <= 50 lines (parity with Python validator)

    Given: All TypeScript/TSX source functions under web/src
    When: Counting lines of code per function
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    ts_files = find_typescript_files()
    if not ts_files:
        pytest.skip("No TypeScript files found under web/src")

    count, violations = scan_function_length_ts(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="function_length_typescript",
        current_count=count,
        violations=violations,
    )
