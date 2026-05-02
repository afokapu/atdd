"""
Detect silent exception swallowing in production Python code.

A silent swallow is a ``try/except`` whose handler:

* makes no observable reaction (no logger call, no ``raise``)
* AND either returns a value or has an empty body

Real incident behind this rule (issue #357): ``seek_opponent_use_case.py``
caught ``match_creator`` errors and returned a broken ``match_id`` for weeks.
The smoke phase exposed it; this validator would have exposed it at GREEN time.

Convention: ``src/atdd/coder/conventions/logging.convention.yaml``
            (rule ``COACH-SILENT-SWALLOW-001``)

Structured violations: emits ``Violation(rule_id="COACH-SILENT-SWALLOW-001", ...)``
records via ``RatchetBaseline.assert_no_regression(violations=...)``.
The rule-id grammar is governed by ``src/atdd/coach/specs/rule-id.spec.md``.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Tuple

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._violation import Violation


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
PYTHON_DIR = REPO_ROOT / "python"
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
LOGGING_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "logging.convention.yaml"

FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "silent_swallow"
)


# ---------------------------------------------------------------------------
# Rule constants (mirrored in logging.convention.yaml::COACH-SILENT-SWALLOW-001)
# ---------------------------------------------------------------------------
RULE_ID = "COACH-SILENT-SWALLOW-001"
RULE_SEVERITY = 4
SUPPRESSION_MARKER = f"atdd:suppress({RULE_ID})"

LOGGER_RECEIVER_NAMES = {
    "logger", "log", "_logger", "_log", "logging", "LOG",
}
LOG_METHODS = {
    "debug", "info", "warning", "warn", "error", "critical", "exception", "log",
}


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------
def _is_excluded(py_file: Path) -> bool:
    """Files we never scan (tests, fixtures, package metadata, caches)."""
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


def _collect_files(*scan_dirs: Path) -> List[Path]:
    """Collect non-test Python files from one or more directories."""
    out: List[Path] = []
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.rglob("*.py"):
            if _is_excluded(py_file):
                continue
            out.append(py_file)
    return out


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def _is_logger_call(node: ast.AST) -> bool:
    """``logger.warning(...)`` / ``self.logger.error(...)`` / ``logging.info(...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in LOG_METHODS:
        return False
    receiver = func.value
    # Match `logger.X`, `log.X`, `logging.X`
    if isinstance(receiver, ast.Name) and receiver.id in LOGGER_RECEIVER_NAMES:
        return True
    # Match `self.logger.X`, `self._logger.X`
    if isinstance(receiver, ast.Attribute) and receiver.attr in LOGGER_RECEIVER_NAMES:
        return True
    return False


def _walk_handler_body(handler: ast.ExceptHandler):
    """Walk handler body but stop at nested function/class definitions.

    A handler that only *defines* a function which logs does NOT count
    as observably reacting to the exception in the handler itself.
    """
    for node in handler.body:
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)) and child is not node:
                # Skip nested scopes when collected from `ast.walk(node)` — the
                # outer iteration over `handler.body` still visits the def itself.
                continue
            yield child


def _handler_has_log_call(handler: ast.ExceptHandler) -> bool:
    return any(_is_logger_call(n) for n in _walk_handler_body(handler))


def _handler_has_raise(handler: ast.ExceptHandler) -> bool:
    """True if the handler unconditionally re-raises or raises a new exception.

    Conservative: a ``raise`` anywhere in the handler body counts. Branches
    that bypass the raise are caught by the explicit-return check.
    """
    return any(isinstance(n, ast.Raise) for n in _walk_handler_body(handler))


def _handler_explicit_returns(handler: ast.ExceptHandler) -> List[ast.Return]:
    """All ``return`` statements in the handler body (excluding nested defs)."""
    returns: List[ast.Return] = []
    for n in _walk_handler_body(handler):
        if isinstance(n, ast.Return):
            returns.append(n)
    return returns


def _handler_body_is_only_pass(handler: ast.ExceptHandler) -> bool:
    """``except X: pass`` (single ``pass`` statement, no other side effects)."""
    return len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)


def _is_suppressed(handler: ast.ExceptHandler, source_lines: List[str]) -> bool:
    """Inline pragma on the ``except`` line silences this rule."""
    if not source_lines:
        return False
    idx = handler.lineno - 1
    if 0 <= idx < len(source_lines):
        if SUPPRESSION_MARKER in source_lines[idx]:
            return True
    return False


def detect_silent_swallows(file_path: Path) -> List[Violation]:
    """Return ``Violation`` records for every silent-swallow handler in *file_path*.

    Detection rules (matching ``COACH-SILENT-SWALLOW-001``):

    * ``except: pass``  — empty body, no observability
    * ``except ...: <body without log + without raise + with explicit return>``
      (return value is irrelevant: any return without observability swallows
      the exception path).

    Any of the following exempt the handler:

    * a ``logger.<level>(...)``, ``self.logger.<level>(...)``,
      ``logging.<level>(...)``, etc. call in the body
    * a ``raise`` statement in the body (re-raise or raise-new)
    * an inline pragma ``# atdd:suppress(COACH-SILENT-SWALLOW-001)`` on the
      ``except`` line.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    source_lines = source.splitlines()

    try:
        rel = file_path.relative_to(REPO_ROOT)
    except ValueError:
        if ATDD_PKG_DIR is not None:
            try:
                rel = file_path.relative_to(ATDD_PKG_DIR.parent)
            except ValueError:
                rel = file_path
        else:
            rel = file_path

    violations: List[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if _is_suppressed(handler, source_lines):
                continue
            if _handler_has_log_call(handler):
                continue
            if _handler_has_raise(handler):
                continue

            returns = _handler_explicit_returns(handler)
            empty_pass = _handler_body_is_only_pass(handler)

            if not returns and not empty_pass:
                # Handler does *something* observable-ish (assignment, function
                # call, etc.) but no return, no raise, no log. We do NOT flag
                # this — the canonical incident shape is a return, and being
                # too aggressive risks false positives on intentional state
                # bookkeeping that lets execution continue past the try.
                continue

            exc_type = "bare except" if handler.type is None else _format_except_clause(handler.type)

            if empty_pass and not returns:
                detail = f"silent swallow ({exc_type}: pass) — no log, no raise"
            else:
                detail = (
                    f"silent swallow ({exc_type}) — no log, no raise; "
                    f"returns from handler ({len(returns)} return statement(s))"
                )

            violations.append(Violation(
                rule_id=RULE_ID,
                severity=RULE_SEVERITY,
                location=f"{rel}:{handler.lineno}",
                detail=detail,
            ))

    return violations


def _format_except_clause(node: ast.AST) -> str:
    """Render ``except SomeError`` / ``except (A, B)`` for the violation detail."""
    try:
        return ast.unparse(node)
    except (AttributeError, ValueError):
        return "<unparsable>"


# ---------------------------------------------------------------------------
# Scan helper for ratchet baseline registry
# ---------------------------------------------------------------------------
def scan_silent_swallows_python(repo_root: Path) -> Tuple[int, List[Violation]]:
    """Aggregate silent-swallow violations across consumer + toolkit Python."""
    scan_dirs: List[Path] = []
    consumer = repo_root / "python"
    if consumer.exists():
        scan_dirs.append(consumer)
    if ATDD_PKG_DIR is not None:
        scan_dirs.append(ATDD_PKG_DIR)
    files = _collect_files(*scan_dirs)
    violations: List[Violation] = []
    for f in files:
        violations.extend(detect_silent_swallows(f))
    return len(violations), violations


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.coder
def test_silent_swallow_fixture_violations_detected():
    """
    SPEC-CODER-SILENT-SWALLOW-0001a: detector finds every seeded violation.

    Given: fixtures/silent_swallow/python_violations/*.py (intentional swallows)
    When:  detect_silent_swallows runs on each fixture
    Then:  every fixture file produces at least one Violation, and the rule_id
           and severity match the convention.
    """
    fixtures_dir = FIXTURES_DIR / "python_violations"
    if not fixtures_dir.exists():
        pytest.fail(f"Missing fixture dir: {fixtures_dir}")

    fixture_files = list(fixtures_dir.rglob("*.py"))
    assert fixture_files, f"No fixture files in {fixtures_dir}"

    for fixture in fixture_files:
        violations = detect_silent_swallows(fixture)
        assert violations, (
            f"Expected silent-swallow violations in {fixture.name} "
            f"but detector found none"
        )
        for v in violations:
            assert v.rule_id == RULE_ID, f"Wrong rule_id: {v.rule_id}"
            assert v.severity == RULE_SEVERITY, f"Wrong severity: {v.severity}"


@pytest.mark.coder
def test_silent_swallow_fixture_clean_no_false_positives():
    """
    SPEC-CODER-SILENT-SWALLOW-0001b: zero false positives on acceptable shapes.

    Given: fixtures/silent_swallow/python_clean/*.py (log+re-raise, log+fallback,
           reraise-with-context, returns-None-after-log, suppression-pragma)
    When:  detect_silent_swallows runs
    Then:  no Violations are produced.
    """
    fixtures_dir = FIXTURES_DIR / "python_clean"
    if not fixtures_dir.exists():
        pytest.fail(f"Missing fixture dir: {fixtures_dir}")

    fixture_files = list(fixtures_dir.rglob("*.py"))
    assert fixture_files, f"No fixture files in {fixtures_dir}"

    spurious: List[str] = []
    for fixture in fixture_files:
        violations = detect_silent_swallows(fixture)
        for v in violations:
            spurious.append(f"  {fixture.name}: {v}")

    if spurious:
        pytest.fail(
            "False positives on acceptable patterns:\n\n"
            + "\n".join(spurious)
        )


@pytest.mark.coder
def test_no_silent_exception_swallowing_python(ratchet_baseline):
    """
    SPEC-CODER-SILENT-SWALLOW-0001: no silent except-swallow regressions.

    Scans REPO_ROOT/python/ (consumer code) and src/atdd/ (toolkit dogfooding)
    for silent exception swallowing. Uses ratchet baseline so pre-existing
    violations are tolerated until they are migrated, but new violations fail.

    Given: production .py files (excluding tests, fixtures, __init__.py)
    When:  AST scan for try/except handlers with no log / no raise that return
    Then:  violation count does not exceed baseline (auto-seeds first run)

    Convention: src/atdd/coder/conventions/logging.convention.yaml
                (rule COACH-SILENT-SWALLOW-001)
    """
    count, violations = scan_silent_swallows_python(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="silent_exception_swallowing_python",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_silent_swallow_rule_declared_in_convention():
    """
    SPEC-CODER-SILENT-SWALLOW-0001c: convention declares the rule.

    Given: src/atdd/coder/conventions/logging.convention.yaml
    When:  loading the file and looking for COACH-SILENT-SWALLOW-001
    Then:  the rule exists with the expected name, severity, and rule id.
    """
    if not LOGGING_CONVENTION.exists():
        pytest.fail(f"Missing convention: {LOGGING_CONVENTION}")

    with open(LOGGING_CONVENTION, "r", encoding="utf-8") as fh:
        convention = yaml.safe_load(fh)

    rules = {r["id"]: r for r in convention.get("rules", [])}
    if RULE_ID not in rules:
        pytest.fail(
            f"Rule {RULE_ID} not found in {LOGGING_CONVENTION}; "
            f"available rule ids: {sorted(rules.keys())}"
        )

    rule = rules[RULE_ID]
    assert rule["severity"] == RULE_SEVERITY, (
        f"Expected severity {RULE_SEVERITY}, got {rule['severity']}"
    )
    assert "no-silent-exception-swallowing" == rule["name"], (
        f"Unexpected rule name: {rule['name']}"
    )
