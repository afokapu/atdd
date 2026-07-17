"""
Test code quality metrics meet minimum standards.

Validates:
- Maintainability index >= 20 (industry standard, via radon)
- Code has appropriate comments
- No code duplication
- Consistent naming conventions

Convention: src/atdd/coder/conventions/refactor.convention.yaml

Structured violations (issue #394): emits ``Violation`` records keyed off
``REFACTOR-QUALITY-*-001`` rule_ids declared in
``src/atdd/coder/conventions/refactor.convention.yaml``.
"""

import pytest
import re
from pathlib import Path
from typing import Dict, List, Tuple

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import resolve_code_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coder.validators.test_duplication_detector import extract_fragments


# Rule bindings — fail at import if conventions drift (issue #394).
_RULE_MI = bind_rule("coder.refactor.quality-mi")
_RULE_COMMENTS = bind_rule("coder.refactor.quality-comments")
_RULE_DUP = bind_rule("coder.refactor.quality-duplication")
_RULE_NAMING = bind_rule("coder.refactor.quality-naming")
_RULE_FILE_LEN = bind_rule("coder.refactor.quality-file-length")

# Path constants
REPO_ROOT = find_repo_root()
PYTHON_DIR = resolve_code_root("python", REPO_ROOT)


# Quality thresholds
# MI >= 20 is "maintainable" per SEI/Microsoft scale (0-100, higher=better)
# MI >= 10 is "moderate", MI < 10 is "unmaintainable"
MIN_MAINTAINABILITY_INDEX = 20
MIN_COMMENT_RATIO = 0.10  # 10% comments
# AST-based: window of N consecutive statements (issue #459). Calibrated against
# src/atdd/ — value 5 keeps real-duplication signal (69 findings full-tree at
# v3.7.5) while clearing the line-based algorithm's re-export false-positives.
# Matches the sister detector's threshold (`coder.duplication.no-intra-layer`).
MIN_DUPLICATE_STATEMENTS = 5


def find_python_files() -> List[Path]:
    """Find all Python source files (excluding tests)."""
    if PYTHON_DIR is None or not PYTHON_DIR.exists():
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
    Calculate maintainability index using radon (standard MI formula).

    The MI formula combines:
    - Halstead volume (operator/operand complexity)
    - Cyclomatic complexity
    - Lines of code
    - Comment percentage (optional, included by default)

    Scale: 0-100 (higher is better)
    - MI >= 20: maintainable
    - 10 <= MI < 20: moderate
    - MI < 10: unmaintainable

    Reference: SEI (Software Engineering Institute) / Microsoft Visual Studio
    """
    try:
        from radon.metrics import mi_visit
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        return mi_visit(source, multi=True)
    except Exception:
        return 100.0  # Can't parse → don't penalize


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


def find_duplicate_code_blocks(
    files: List[Path],
) -> List[Tuple[Path, Path, int, int]]:
    """
    Find structurally duplicate code fragments across files (issue #459).

    Uses the AST-normalized sliding-window matcher from
    ``test_duplication_detector.extract_fragments`` (Name nodes → ``"VAR"``,
    constants → ``0``/``""``). A window of ``MIN_DUPLICATE_STATEMENTS``
    consecutive statements that hashes equal across two different files is a
    violation.

    The rule is rename-insensitive: structurally identical functions with
    different identifier names ARE flagged — that's the intended new behavior.

    Re-export blocks (``from .x import (A, B, C, D, E)``) and other lexically-
    similar-but-structurally-different windows do NOT match: each import is one
    AST statement, so a 5-statement window almost never collides across
    unrelated files. The previous hardcoded ABC/dataclass exclusion is
    subsumed by this normalization and has been removed.

    Returns:
        List of ``(file_a, file_b, start_line_a, end_line_a)`` tuples — one per
        unique ``(file_a, file_b, fragment_hash)`` collision. Line range refers
        to the fragment as it appears in ``file_a``.
    """
    # hash → list of (file, start_line, end_line)
    hash_map: Dict[str, List[Tuple[Path, int, int]]] = {}
    for f in files:
        for h, start, end in extract_fragments(f, MIN_DUPLICATE_STATEMENTS):
            hash_map.setdefault(h, []).append((f, start, end))

    seen_pairs: set = set()
    duplicates: List[Tuple[Path, Path, int, int]] = []
    for h, locations in hash_map.items():
        unique_files = {loc[0] for loc in locations}
        if len(unique_files) < 2:
            continue
        first = locations[0]
        for other in locations[1:]:
            if other[0] == first[0]:
                continue
            key = (first[0], other[0], h)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            duplicates.append((first[0], other[0], first[1], first[2]))

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


FILE_LINE_REPORT_THRESHOLD = 500


def scan_file_line_count(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for files exceeding the line-count report threshold. Used by ratchet baseline.

    There is no hard limit — the ratchet baseline prevents growth.  Files over
    FILE_LINE_REPORT_THRESHOLD (500) are tracked so that their line count
    cannot increase without an explicit baseline update.
    """
    python_dir = resolve_code_root("python", repo_root)
    if python_dir is None or not python_dir.exists():
        return 0, []
    files = []
    for py_file in python_dir.rglob("*.py"):
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            continue
        if '__pycache__' in str(py_file):
            continue
        files.append(py_file)
    violations: List[Violation] = []
    for py_file in files:
        try:
            line_count = len(py_file.read_text(encoding='utf-8').splitlines())
        except Exception:
            continue
        if line_count > FILE_LINE_REPORT_THRESHOLD:
            rel_path = py_file.relative_to(repo_root)
            violations.append(Violation(
                rule_id=_RULE_FILE_LEN.rule_id,
                severity=_RULE_FILE_LEN.severity,
                location=f"{rel_path}:1",
                detail=f"{rel_path} lines={line_count}",
                fix_hint_ref=_RULE_FILE_LEN.fix_hint_ref,
            ))
    return len(violations), violations


@pytest.mark.coder
def test_maintainability_index_above_threshold():
    """
    SPEC-CODER-QUALITY-0001: Code has acceptable maintainability index.

    Uses radon's standard MI formula (Halstead volume + cyclomatic complexity + LOC).
    Threshold: MI >= 20 (SEI/Microsoft "maintainable" threshold).
    Uses ratchet baseline to prevent regression while allowing incremental fixes.

    Given: All Python files
    When: Calculating maintainability index via radon
    Then: Violation count does not exceed baseline
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    violations: List[Violation] = []

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
            violations.append(Violation(
                rule_id=_RULE_MI.rule_id,
                severity=_RULE_MI.severity,
                location=f"{rel_path}:1",
                detail=f"Maintainability Index: {index:.1f} (min: {MIN_MAINTAINABILITY_INDEX})",
                fix_hint_ref=_RULE_MI.fix_hint_ref,
            ))

    assert_disposition_satisfied(
        validator_id="maintainability_index",
        violations=violations,
    )


@pytest.mark.coder
def test_adequate_code_comments():
    """
    SPEC-CODER-QUALITY-0002: Code has adequate comments.

    Well-commented code is easier to maintain.
    Threshold: > 10% comment ratio.
    Uses ratchet baseline to prevent regression.

    Given: All Python files
    When: Calculating comment ratio
    Then: Violation count does not exceed baseline
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    violations: List[Violation] = []

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
            violations.append(Violation(
                rule_id=_RULE_COMMENTS.rule_id,
                severity=_RULE_COMMENTS.severity,
                location=f"{rel_path}:1",
                detail=f"Comment ratio: {ratio*100:.1f}% (min: {MIN_COMMENT_RATIO*100:.0f}%)",
                fix_hint_ref=_RULE_COMMENTS.fix_hint_ref,
            ))

    assert_disposition_satisfied(
        validator_id="code_comments",
        violations=violations,
    )


@pytest.mark.coder
def test_no_significant_code_duplication():
    """
    SPEC-CODER-QUALITY-0003: No significant code duplication.

    Duplicate code should be extracted into functions or shared helpers.

    Threshold: ``MIN_DUPLICATE_STATEMENTS`` consecutive AST statements whose
    normalized form (variable names → ``"VAR"``, constants → ``0``/``""``)
    hashes equal across two different files. Issue #459 replaced the legacy
    line-based algorithm; the per-file ``[:50]`` cap is gone — AST scans the
    full tree in seconds.

    Given: All Python files
    When: Comparing AST statement windows by hash
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    duplicates = find_duplicate_code_blocks(python_files)
    violations: List[Violation] = []
    for file_a, file_b, start_line, end_line in duplicates:
        rel_a = file_a.relative_to(REPO_ROOT)
        rel_b = file_b.relative_to(REPO_ROOT)
        span = end_line - start_line + 1
        violations.append(Violation(
            rule_id=_RULE_DUP.rule_id,
            severity=_RULE_DUP.severity,
            location=f"{rel_a}:{start_line}",
            detail=(
                f"{rel_a}:{start_line}-{end_line} <-> {rel_b} "
                f"({MIN_DUPLICATE_STATEMENTS} identical statements, {span} lines)"
            ),
            fix_hint_ref=_RULE_DUP.fix_hint_ref,
        ))

    assert_disposition_satisfied(
        validator_id="code_duplication",
        violations=violations,
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
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found")

    all_violations: List[Violation] = []

    for py_file in python_files:
        violations = check_naming_consistency(py_file)
        if violations:
            rel_path = py_file.relative_to(REPO_ROOT)
            for v in violations:
                all_violations.append(Violation(
                    rule_id=_RULE_NAMING.rule_id,
                    severity=_RULE_NAMING.severity,
                    location=f"{rel_path}:1",
                    detail=v,
                    fix_hint_ref=_RULE_NAMING.fix_hint_ref,
                ))

    assert_disposition_satisfied(
        validator_id="naming_conventions",
        violations=all_violations,
    )


@pytest.mark.coder
def test_file_line_count():
    """
    SPEC-CODER-FILELINES-0001: File line count tracked via ratchet.

    No hard limit on file length — comments, imports, type annotations, and
    constants inflate line count without adding complexity.  A hard limit
    creates false positives and encourages artificial splitting.

    The ratchet baseline prevents *growth*: a 600-line file is baselined,
    but growing it to 700 without an explicit baseline update will fail.
    Files under FILE_LINE_REPORT_THRESHOLD (500 lines) are not tracked.

    Given: All Python source files
    When: Counting total lines per file
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_files = find_python_files()
    if not python_files:
        pytest.skip("No Python files found")

    count, violations = scan_file_line_count(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id="file_line_count",
        violations=violations,
    )
