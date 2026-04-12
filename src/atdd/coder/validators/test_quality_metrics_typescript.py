"""
Test TypeScript/TSX code quality metrics meet minimum standards.

Validates:
- Maintainability Index >= 20 (approximation without radon — uses
  Halstead-lite volume, cyclomatic complexity proxy, and LOC)
- Comment ratio >= 10% (inline // comments, block /* */ comments, JSDoc)

Regex-based — no AST parser or tree-sitter dependency.
Same thresholds as the Python counterpart (test_quality_metrics.py).
Uses ratchet baseline to prevent regression.

Convention: src/atdd/coder/conventions/quality.convention.yaml
"""

import math
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
# Quality thresholds (parity with test_quality_metrics.py)
# ---------------------------------------------------------------------------
MIN_MAINTAINABILITY_INDEX = 20
MIN_COMMENT_RATIO = 0.10  # 10%

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
        if ".test." in ts_file.name or ".spec." in ts_file.name:
            continue
        if ts_file.name.startswith("test_") or "/tests/" in str(ts_file):
            continue
        files.append(ts_file)

    return files


# ---------------------------------------------------------------------------
# Maintainability Index approximation
# ---------------------------------------------------------------------------
#
# The standard MI formula (SEI / Visual Studio):
#   MI = 171 - 5.2 * ln(V) - 0.23 * CC - 16.2 * ln(LOC) + 50 * sin(sqrt(2.4 * CM))
#
# Where:
#   V  = Halstead volume
#   CC = average cyclomatic complexity per function
#   LOC = lines of code
#   CM = comment ratio (0..1)
#
# Since we have no AST, we approximate Halstead volume from operator/operand
# counts via regex.  This gives a directionally correct MI that is comparable
# across files within the same codebase — sufficient for ratchet tracking.
# ---------------------------------------------------------------------------

_OPERATORS = re.compile(
    r"(?:"
    r"===|!==|==|!=|>=|<=|=>|&&|\|\||>>>=|>>>|>>=|<<=|"
    r"\?\?|\?\.|[+\-*/%&|^~!<>=]=?|"
    r"\.\.\.|"
    r"[{}()\[\];,.:?]"
    r")"
)

_OPERANDS = re.compile(
    r"""(?:"""
    r""""(?:[^"\\]|\\.)*"|"""
    r"""'(?:[^'\\]|\\.)*'|"""
    r"""`(?:[^`\\]|\\.)*`|"""
    r"""\b\d[\d_.eExXbBoO]*\b|"""
    r"""\b[a-zA-Z_$][a-zA-Z0-9_$]*\b"""
    r""")"""
)

# Rough cyclomatic-complexity keywords for MI formula
_CC_KEYWORDS = re.compile(
    r"\b(?:if|else\s+if|for|while|do|catch|case|&&|\|\|)\b"
)


def _halstead_volume(source: str) -> float:
    """Approximate Halstead volume from operator/operand regex counts."""
    operators = _OPERATORS.findall(source)
    operands = _OPERANDS.findall(source)

    n1 = len(set(operators))  # unique operators
    n2 = len(set(operands))   # unique operands
    N1 = len(operators)       # total operators
    N2 = len(operands)        # total operands

    n = n1 + n2  # vocabulary
    N = N1 + N2  # length

    if n <= 1:
        return 1.0
    return N * math.log2(n)


def calculate_maintainability_index_ts(file_path: Path) -> float:
    """
    Calculate an approximate Maintainability Index for a TypeScript file.

    Uses the SEI formula with regex-approximated Halstead volume.
    Returns a value on the 0-171 scale (clamped to 0-100 for display).
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception:
        return 100.0  # can't parse — don't penalize

    # Strip comments for code metrics (keep for comment ratio separately)
    code = _strip_comments(source)
    loc = sum(1 for line in code.split("\n") if line.strip())

    if loc == 0:
        return 100.0

    V = _halstead_volume(code)
    if V <= 0:
        V = 1.0

    # Avg cyclomatic complexity across the file (rough)
    cc_matches = _CC_KEYWORDS.findall(source)
    # Estimate function count (very rough)
    func_count = max(
        1,
        len(re.findall(r"\bfunction\b", source))
        + len(re.findall(r"=>\s*[{(]", source)),
    )
    avg_cc = max(1, len(cc_matches)) / func_count

    # Comment ratio
    cm = _comment_ratio_from_source(source)

    # MI formula
    mi = (
        171
        - 5.2 * math.log(V)
        - 0.23 * avg_cc
        - 16.2 * math.log(loc)
        + 50.0 * math.sin(math.sqrt(2.4 * cm))
    )

    return max(0.0, min(100.0, mi))


def _strip_comments(source: str) -> str:
    """Remove single-line and block comments from TypeScript source."""
    # Remove block comments (non-greedy)
    result = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    # Remove single-line comments
    result = re.sub(r"//[^\n]*", "", result)
    return result


# ---------------------------------------------------------------------------
# Comment ratio
# ---------------------------------------------------------------------------
def _comment_ratio_from_source(source: str) -> float:
    """Calculate comment ratio from raw source text."""
    lines = source.split("\n")
    total_non_blank = 0
    comment_lines = 0
    in_block_comment = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        total_non_blank += 1

        if in_block_comment:
            comment_lines += 1
            if "*/" in stripped:
                in_block_comment = False
            continue

        if stripped.startswith("/*"):
            comment_lines += 1
            if "*/" not in stripped:
                in_block_comment = True
            continue

        if stripped.startswith("//"):
            comment_lines += 1
            continue

        # JSDoc-style: lines starting with * inside /** ... */
        if stripped.startswith("*"):
            comment_lines += 1
            continue

    return comment_lines / total_non_blank if total_non_blank > 0 else 0.0


def calculate_comment_ratio_ts(file_path: Path) -> float:
    """Calculate comment ratio for a TypeScript file."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception:
        return 0.0

    return _comment_ratio_from_source(source)


# ---------------------------------------------------------------------------
# Scan functions (used by ratchet baseline registration)
# ---------------------------------------------------------------------------
def scan_maintainability_index_ts(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for MI violations in TS/TSX files. Used by ratchet baseline."""
    web_src = repo_root / "web" / "src"
    if not web_src.exists():
        return 0, []

    files = find_typescript_files(web_src)
    violations: List[str] = []

    for ts_file in files:
        try:
            content = ts_file.read_text(encoding="utf-8")
            if len(content.split("\n")) < 10:
                continue
        except Exception:
            continue

        mi = calculate_maintainability_index_ts(ts_file)
        if mi < MIN_MAINTAINABILITY_INDEX:
            rel_path = ts_file.relative_to(repo_root)
            violations.append(f"{rel_path} MI={mi:.1f}")

    return len(violations), violations


def scan_comment_ratio_ts(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for comment ratio violations in TS/TSX files. Used by ratchet baseline."""
    web_src = repo_root / "web" / "src"
    if not web_src.exists():
        return 0, []

    files = find_typescript_files(web_src)
    violations: List[str] = []

    for ts_file in files:
        try:
            content = ts_file.read_text(encoding="utf-8")
            if len(content.split("\n")) < 20:
                continue
        except Exception:
            continue

        ratio = calculate_comment_ratio_ts(ts_file)
        if ratio < MIN_COMMENT_RATIO:
            rel_path = ts_file.relative_to(repo_root)
            violations.append(f"{rel_path} {ratio * 100:.1f}%")

    return len(violations), violations


# ---------------------------------------------------------------------------
# Pytest tests
# ---------------------------------------------------------------------------
@pytest.mark.coder
def test_maintainability_index_typescript(ratchet_baseline):
    """
    SPEC-CODER-QUALITY-TS-0001: TS code has acceptable maintainability index.

    Uses an approximate MI formula (SEI / Visual Studio) with regex-based
    Halstead volume estimation. No radon dependency — pure regex.

    Threshold: MI >= 20 (SEI "maintainable" threshold, parity with Python)

    Given: All TypeScript/TSX source files under web/src (>=10 lines)
    When: Calculating approximate maintainability index
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    ts_files = find_typescript_files()
    if not ts_files:
        pytest.skip("No TypeScript files found under web/src")

    count, violations = scan_maintainability_index_ts(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="maintainability_index_typescript",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_comment_ratio_typescript(ratchet_baseline):
    """
    SPEC-CODER-QUALITY-TS-0002: TS code has adequate comments.

    Counts //, /* */, and JSDoc comment lines vs total non-blank lines.

    Threshold: >= 10% comment ratio (parity with Python validator)

    Given: All TypeScript/TSX source files under web/src (>=20 lines)
    When: Calculating comment line ratio
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    ts_files = find_typescript_files()
    if not ts_files:
        pytest.skip("No TypeScript files found under web/src")

    count, violations = scan_comment_ratio_ts(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="comment_ratio_typescript",
        current_count=count,
        violations=violations,
    )
