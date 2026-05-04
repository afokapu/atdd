# URN: component:govern-lifecycle:enforcement-substrate:test_toolkit_source_layout_assumptions:backend:domain
# Runtime: python
# Purpose: Detect toolkit-source-vs-installed layout assumptions in atdd's own source.

"""
Detect two recurring anti-patterns where toolkit code assumes the
toolkit-self repo layout (``src/atdd/``) or assumes atdd is pip-installed,
breaking the other shape silently.

Pattern A — ``COACH-PKG-LAYOUT-001`` (toolkit-self layout assumption):
    ``find_repo_root()`` followed by path arithmetic that descends into
    ``src/atdd/...``. Works in toolkit-self, raises ``FileNotFoundError``
    in any pip-installed consumer.

Pattern B — ``COACH-PKG-LAYOUT-002`` (install-detection assumption):
    Bare ``version("atdd")`` / ``pkg_version("atdd")`` /
    ``importlib.metadata.version("atdd")`` outside the canonical
    try/except wrapper in ``src/atdd/__init__.py``. Raises
    ``PackageNotFoundError`` when atdd runs from source without a wheel
    installed (CI's exact setup).

Real incidents (3 in two days, 2026-05-01..02): #341 (pytest argv0 / PATH),
#352 (pkg_version in cli.py), #367 (find_repo_root + src/atdd in three coach
validators). Each took 30+ minutes to root-cause; this validator catches the
4th.

Convention: ``src/atdd/coach/conventions/source-layout.convention.yaml``
SPEC:       ``src/atdd/coach/specs/toolkit-source-layout.spec.md``

Suppression: ``# atdd:suppress(coach.source-layout.toolkit-code-must-not)`` /
``# atdd:suppress(coach.source-layout.toolkit-code-must-not-1)`` on the offending line per the
grammar in #357.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Tuple

import pytest
import yaml

import atdd
from atdd.coach.validators._violation import Violation


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
SOURCE_LAYOUT_CONVENTION = (
    ATDD_PKG_DIR / "coach" / "conventions" / "source-layout.convention.yaml"
)

FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "toolkit_source_layout"
)


# ---------------------------------------------------------------------------
# Rule constants (mirrored in source-layout.convention.yaml)
# ---------------------------------------------------------------------------
RULE_A_ID = "COACH-PKG-LAYOUT-001"
RULE_B_ID = "COACH-PKG-LAYOUT-002"
RULE_SEVERITY = 4

SUPPRESSION_MARKER_A = f"atdd:suppress({RULE_A_ID})"
SUPPRESSION_MARKER_B = f"atdd:suppress({RULE_B_ID})"

VERSION_FUNC_NAMES = {"version", "pkg_version"}


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------
def _is_excluded(py_file: Path) -> bool:
    """Files we never scan (tests, fixtures, package metadata, caches).

    ``__init__.py`` is the canonical home of the ``version("atdd")``
    try/except wrapper and is never scanned for either rule.
    """
    path_str = str(py_file)
    if "/tests/" in path_str or "/test/" in path_str:
        return True
    if "/fixtures/" in path_str:
        return True
    if py_file.name.startswith("test_"):
        return True
    if py_file.name.endswith("_test.py"):
        return True
    if py_file.name == "conftest.py":
        return True
    if "__pycache__" in path_str:
        return True
    if py_file.name == "__init__.py":
        return True
    return False


def _collect_files(scan_dir: Path) -> List[Path]:
    if not scan_dir.exists():
        return []
    return [f for f in scan_dir.rglob("*.py") if not _is_excluded(f)]


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------
def _is_suppressed(
    node: ast.AST, source_lines: List[str], marker: str
) -> bool:
    """Inline pragma on the offending line silences the rule.

    The pragma may sit on the start line of the call expression — for
    multi-line constructs the marker is checked across the line range
    spanned by the AST node.
    """
    if not source_lines:
        return False
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None) or start
    if start is None:
        return False
    for lineno in range(start, end + 1):
        idx = lineno - 1
        if 0 <= idx < len(source_lines) and marker in source_lines[idx]:
            return True
    return False


# ---------------------------------------------------------------------------
# Pattern A: find_repo_root() + src/atdd path arithmetic
# ---------------------------------------------------------------------------
def _binop_div_chain_operands(node: ast.AST) -> List[ast.AST]:
    """Flatten a left-deep chain of ``a / b / c / ...`` BinOps into operands.

    Returns the leaves of the division chain in left-to-right order.
    Non-division BinOps and other node shapes are returned as a single leaf.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _binop_div_chain_operands(node.left) + [node.right]
    return [node]


def _operand_invokes_find_repo_root(operand: ast.AST) -> bool:
    """``find_repo_root()`` direct call, optionally wrapped in ``or`` / ``Path()``.

    Recognized shapes:

    * ``find_repo_root()``
    * ``(x or find_repo_root())``
    * ``Path(find_repo_root())``
    """
    if isinstance(operand, ast.Call):
        func = operand.func
        if isinstance(func, ast.Name) and func.id == "find_repo_root":
            return True
        # Path(find_repo_root()) — descend one level
        if (
            isinstance(func, ast.Name)
            and func.id == "Path"
            and len(operand.args) == 1
        ):
            return _operand_invokes_find_repo_root(operand.args[0])
    if isinstance(operand, ast.BoolOp):
        return any(
            _operand_invokes_find_repo_root(v) for v in operand.values
        )
    return False


def _string_segments_in_chain(operands: List[ast.AST]) -> List[str]:
    """Concatenate string-literal operands in the chain into a single path
    string for sequence matching.

    ``find_repo_root() / "src" / "atdd" / "coach"`` → ``"/src/atdd/coach"``
    ``find_repo_root() / "src/atdd/coach"``         → ``"/src/atdd/coach"``
    Non-string operands (e.g. ``Path()`` calls, names) are dropped.
    """
    parts: List[str] = []
    for op in operands:
        if isinstance(op, ast.Constant) and isinstance(op.value, str):
            parts.append(op.value.strip("/"))
    return parts


def _chain_descends_into_src_atdd(operands: List[ast.AST]) -> bool:
    """True iff the string segments of the chain include ``src`` then ``atdd``
    consecutively (or a single segment containing ``src/atdd``).
    """
    segments = _string_segments_in_chain(operands)
    joined = "/".join(segments)
    return "src/atdd" in joined


def _detect_pattern_a(
    tree: ast.AST, source_lines: List[str]
) -> List[Tuple[int, str]]:
    """Return ``(lineno, detail)`` for every Pattern A violation in *tree*."""
    hits: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
            continue
        operands = _binop_div_chain_operands(node)
        if not operands:
            continue
        if not _operand_invokes_find_repo_root(operands[0]):
            continue
        if not _chain_descends_into_src_atdd(operands[1:]):
            continue
        # Only flag the outermost BinOp of the chain — skip inner BinOps so a
        # single offending expression produces a single violation.
        parent_is_div = False
        for outer in ast.walk(tree):
            if (
                isinstance(outer, ast.BinOp)
                and isinstance(outer.op, ast.Div)
                and (outer.left is node)
            ):
                parent_is_div = True
                break
        if parent_is_div:
            continue
        if _is_suppressed(node, source_lines, SUPPRESSION_MARKER_A):
            continue
        try:
            expr = ast.unparse(node)
        except (AttributeError, ValueError):
            expr = "<unparsable>"
        detail = (
            f"find_repo_root() + 'src/atdd/...' assumes toolkit-self layout: "
            f"{expr}. Use Path(atdd.__file__).resolve().parent instead."
        )
        hits.append((node.lineno, detail))
    return hits


# ---------------------------------------------------------------------------
# Pattern B: bare version("atdd") outside try/except wrapper
# ---------------------------------------------------------------------------
def _is_version_call_for_atdd(node: ast.Call) -> bool:
    """``version("atdd")`` / ``pkg_version("atdd")`` / ``importlib.metadata.version("atdd")``."""
    if not node.args:
        return False
    arg0 = node.args[0]
    if not (isinstance(arg0, ast.Constant) and arg0.value == "atdd"):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id in VERSION_FUNC_NAMES:
        return True
    if isinstance(func, ast.Attribute) and func.attr in VERSION_FUNC_NAMES:
        return True
    return False


def _enclosing_try_handlers_catch_packagenotfound(
    parents: List[ast.AST],
) -> bool:
    """A ``try`` ancestor whose handler list catches ``PackageNotFoundError``
    is the canonical wrapper — calls inside it are exempt.
    """
    for ancestor in parents:
        if not isinstance(ancestor, ast.Try):
            continue
        for h in ancestor.handlers:
            if h.type is None:
                return True
            try:
                spelled = ast.unparse(h.type)
            except (AttributeError, ValueError):
                spelled = ""
            if "PackageNotFoundError" in spelled or spelled == "Exception":
                return True
    return False


def _walk_with_parents(tree: ast.AST):
    """Yield ``(node, parents)`` pairs over the AST."""
    stack: List[Tuple[ast.AST, List[ast.AST]]] = [(tree, [])]
    while stack:
        node, parents = stack.pop()
        yield node, parents
        new_parents = parents + [node]
        for child in ast.iter_child_nodes(node):
            stack.append((child, new_parents))


def _detect_pattern_b(
    tree: ast.AST, source_lines: List[str]
) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    for node, parents in _walk_with_parents(tree):
        if not (isinstance(node, ast.Call) and _is_version_call_for_atdd(node)):
            continue
        if _enclosing_try_handlers_catch_packagenotfound(parents):
            continue
        if _is_suppressed(node, source_lines, SUPPRESSION_MARKER_B):
            continue
        try:
            expr = ast.unparse(node)
        except (AttributeError, ValueError):
            expr = "<unparsable>"
        detail = (
            f"bare {expr} assumes atdd is pip-installed; raises "
            f"PackageNotFoundError when running from source. "
            f"Use 'from atdd import __version__' instead."
        )
        hits.append((node.lineno, detail))
    return hits


# ---------------------------------------------------------------------------
# Per-file detection
# ---------------------------------------------------------------------------
def detect_layout_violations(file_path: Path) -> List[Violation]:
    """Return ``Violation`` records for every Pattern A and Pattern B hit."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    source_lines = source.splitlines()
    try:
        rel = file_path.relative_to(ATDD_PKG_DIR.parent)
    except ValueError:
        rel = file_path

    violations: List[Violation] = []
    for lineno, detail in _detect_pattern_a(tree, source_lines):
        violations.append(
            Violation(
                rule_id=RULE_A_ID,
                severity=RULE_SEVERITY,
                location=f"{rel}:{lineno}",
                detail=detail,
                fix_hint_ref="recipe:source-layout#pattern-a",
            )
        )
    for lineno, detail in _detect_pattern_b(tree, source_lines):
        violations.append(
            Violation(
                rule_id=RULE_B_ID,
                severity=RULE_SEVERITY,
                location=f"{rel}:{lineno}",
                detail=detail,
                fix_hint_ref="recipe:source-layout#pattern-b",
            )
        )
    return violations


def scan_toolkit_source_layout() -> Tuple[int, List[Violation]]:
    """Aggregate violations across the toolkit's own Python source."""
    files = _collect_files(ATDD_PKG_DIR)
    violations: List[Violation] = []
    for f in files:
        violations.extend(detect_layout_violations(f))
    return len(violations), violations


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.coach
def test_pattern_a_violations_detected():
    """SPEC-COACH-PKG-LAYOUT-0001a: Pattern A detector finds every seeded violation.

    Given: ``fixtures/toolkit_source_layout/pattern_a_violation.py``
    When:  ``detect_layout_violations`` runs on the fixture
    Then:  every ``find_repo_root() / 'src/atdd/...'`` shape produces a
           Violation tagged ``COACH-PKG-LAYOUT-001`` (severity 4) and the
           four seeded distinct shapes are all flagged.
    """
    fixture = FIXTURES_DIR / "pattern_a_violation.py"
    assert fixture.exists(), f"Missing fixture: {fixture}"

    violations = [
        v
        for v in detect_layout_violations(fixture)
        if v.rule_id == RULE_A_ID
    ]
    assert violations, "Expected COACH-PKG-LAYOUT-001 violations in fixture"

    for v in violations:
        assert v.severity == RULE_SEVERITY
        assert "src/atdd" in v.detail or "find_repo_root" in v.detail

    # Distinct seeded shapes (direct, single literal, or-short-circuit,
    # nested Path()) should each produce at least one violation. Variable
    # indirection (``REPO_ROOT = find_repo_root(); REPO_ROOT / 'src' / 'atdd'``)
    # is documented out of scope — see the SPEC's "Limits" section.
    assert len(violations) >= 4, (
        f"Expected ≥4 distinct Pattern A hits, got {len(violations)}: "
        f"{[v.location for v in violations]}"
    )


@pytest.mark.coach
def test_pattern_a_clean_no_false_positives():
    """SPEC-COACH-PKG-LAYOUT-0001b: Pattern A clean shapes produce zero Violations.

    Given: ``fixtures/toolkit_source_layout/pattern_a_clean.py``
    When:  ``detect_layout_violations`` runs
    Then:  no COACH-PKG-LAYOUT-001 violations are produced (canonical
           Path(atdd.__file__) recipes, consumer-repo paths, suppressed sites).
    """
    fixture = FIXTURES_DIR / "pattern_a_clean.py"
    assert fixture.exists(), f"Missing fixture: {fixture}"

    spurious = [
        v
        for v in detect_layout_violations(fixture)
        if v.rule_id == RULE_A_ID
    ]
    if spurious:
        pytest.fail(
            "False positives on COACH-PKG-LAYOUT-001 clean shapes:\n"
            + "\n".join(f"  {v}" for v in spurious)
        )


@pytest.mark.coach
def test_pattern_b_violations_detected():
    """SPEC-COACH-PKG-LAYOUT-0002a: Pattern B detector finds every seeded violation.

    Given: ``fixtures/toolkit_source_layout/pattern_b_violation.py``
    When:  ``detect_layout_violations`` runs on the fixture
    Then:  every bare ``version("atdd")``/``pkg_version("atdd")``/qualified
           ``importlib.metadata.version("atdd")`` outside a try/except
           PackageNotFoundError wrapper produces COACH-PKG-LAYOUT-002.
    """
    fixture = FIXTURES_DIR / "pattern_b_violation.py"
    assert fixture.exists(), f"Missing fixture: {fixture}"

    violations = [
        v
        for v in detect_layout_violations(fixture)
        if v.rule_id == RULE_B_ID
    ]
    assert violations, "Expected COACH-PKG-LAYOUT-002 violations in fixture"
    for v in violations:
        assert v.severity == RULE_SEVERITY
        assert "atdd" in v.detail
    assert len(violations) >= 4, (
        f"Expected ≥4 distinct Pattern B hits, got {len(violations)}: "
        f"{[v.location for v in violations]}"
    )


@pytest.mark.coach
def test_pattern_b_clean_no_false_positives():
    """SPEC-COACH-PKG-LAYOUT-0002b: Pattern B clean shapes produce zero Violations.

    Given: ``fixtures/toolkit_source_layout/pattern_b_clean.py``
    When:  ``detect_layout_violations`` runs
    Then:  no COACH-PKG-LAYOUT-002 violations on ``__version__`` import,
           try/except wrapper, version("other-pkg"), or suppressed sites.
    """
    fixture = FIXTURES_DIR / "pattern_b_clean.py"
    assert fixture.exists(), f"Missing fixture: {fixture}"

    spurious = [
        v
        for v in detect_layout_violations(fixture)
        if v.rule_id == RULE_B_ID
    ]
    if spurious:
        pytest.fail(
            "False positives on COACH-PKG-LAYOUT-002 clean shapes:\n"
            + "\n".join(f"  {v}" for v in spurious)
        )


@pytest.mark.coach
def test_no_toolkit_source_layout_assumptions():
    """SPEC-COACH-PKG-LAYOUT-0003: zero layout violations across atdd's own source.

    Scans ``src/atdd/`` for both Pattern A and Pattern B and asserts that
    every hit is either suppressed via inline pragma or absent. Hard-fails
    on regression — past 3 incidents (#341, #352, #367) cost 30+ minutes
    each to root-cause.
    """
    count, violations = scan_toolkit_source_layout()
    if count > 0:
        formatted = "\n".join(f"  {v}" for v in violations)
        pytest.fail(
            f"Found {count} toolkit-source-layout violation(s):\n{formatted}\n"
            f"Convention: src/atdd/coach/conventions/source-layout.convention.yaml\n"
            f"SPEC:       src/atdd/coach/specs/toolkit-source-layout.spec.md"
        )


@pytest.mark.coach
def test_source_layout_convention_declares_rules():
    """SPEC-COACH-PKG-LAYOUT-0004: convention declares both rules with stable IDs.

    Given: ``src/atdd/coach/conventions/source-layout.convention.yaml``
    When:  loading and indexing rules by id
    Then:  ``COACH-PKG-LAYOUT-001`` and ``COACH-PKG-LAYOUT-002`` are
           declared with severity 4.
    """
    if not SOURCE_LAYOUT_CONVENTION.exists():
        pytest.fail(f"Missing convention: {SOURCE_LAYOUT_CONVENTION}")

    with open(SOURCE_LAYOUT_CONVENTION, "r", encoding="utf-8") as fh:
        convention = yaml.safe_load(fh)

    rules = {r["id"]: r for r in convention.get("rules", [])}
    for rule_id in (RULE_A_ID, RULE_B_ID):
        if rule_id not in rules:
            pytest.fail(
                f"Rule {rule_id} not found in {SOURCE_LAYOUT_CONVENTION}; "
                f"available: {sorted(rules.keys())}"
            )
        assert rules[rule_id]["severity"] == RULE_SEVERITY, (
            f"{rule_id}: expected severity {RULE_SEVERITY}, "
            f"got {rules[rule_id]['severity']}"
        )
