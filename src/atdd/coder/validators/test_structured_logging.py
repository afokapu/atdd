"""
Test structured logging conventions are followed.

Validates:
- No print() calls in non-test production Python code (LOGGING-PRINT-001)
- Logger calls include extra= keyword for structured context (LOGGING-STRUCTURED-001)

Conventions from:
- atdd/coder/conventions/logging.convention.yaml

Scan scope:
- REPO_ROOT/python/ (consumer product code)
- ATDD_PKG_DIR (src/atdd/ — toolkit dogfooding)

LOGGING-PRINT-001 exemptions:
- ATDD toolkit (src/atdd/) — CLI tool where print() is the primary output mechanism
- LOGGING-PRINT-001 only applies to consumer product code (python/)

Structured violations (issue #394): emits ``Violation`` records keyed off
``LOGGING-PRINT-001`` and ``LOGGING-STRUCTURED-001``.
"""

import pytest
import ast
from pathlib import Path
from typing import List, Tuple

import atdd
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import resolve_code_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation


# Rule bindings — fail at import if conventions drift (issue #394).
_RULE_PRINT = bind_rule("coder.logging.print")
_RULE_STRUCTURED = bind_rule("coder.logging.structured")


# Path constants
# Consumer repo artifacts
REPO_ROOT = find_repo_root()
PYTHON_DIR = resolve_code_root("python", REPO_ROOT)

# Package resources (conventions, schemas)
# PKG_DIR always resolves to the installed atdd package (used for loading
# bundled resources like conventions/schemas, regardless of install mode).
PKG_DIR = Path(atdd.__file__).resolve().parent
LOGGING_CONVENTION = PKG_DIR / "coder" / "conventions" / "logging.convention.yaml"


# Path components that indicate a pip-installed/vendored location rather
# than the atdd source tree. Even when a consumer repo has its .venv inside
# the repo root, atdd.__file__ under any of these must not be dogfood-scanned.
_VENDORED_PATH_MARKERS = frozenset(
    {
        "site-packages",
        ".venv",
        "venv",
        ".tox",
        "__pypackages__",
        "node_modules",
    }
)


def _atdd_source_dir_or_none() -> Path | None:
    """
    Return the atdd package directory only when running inside the atdd
    source repo (editable/source install: ``atdd.__file__`` lives under
    ``REPO_ROOT`` and NOT inside a vendored/virtualenv directory).

    When atdd is pip-installed into a consumer repo — even into a ``.venv``
    that happens to sit inside the consumer's repo root — ``atdd.__file__``
    points inside site-packages and MUST NOT be scanned as "toolkit
    dogfooding", or it would raise spurious LOG violations against vendored
    code.
    """
    try:
        pkg_dir = Path(atdd.__file__).resolve().parent
    except (AttributeError, TypeError):
        return None
    try:
        pkg_dir.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return None
    if any(part in _VENDORED_PATH_MARKERS for part in pkg_dir.parts):
        return None
    return pkg_dir


# ATDD_PKG_DIR is ONLY set when running inside the atdd source repo.
# In consumer repos with pip-installed atdd it is None, and dogfooding scans
# are skipped.
ATDD_PKG_DIR = _atdd_source_dir_or_none()

# Logger method names that require extra= for structured context
LOG_METHODS = {"debug", "info", "warning", "error", "critical", "exception", "log"}

# Receiver variable names that indicate a logging call (not Streamlit st.info, etc.)
LOGGER_RECEIVER_NAMES = {"logger", "log", "_logger", "_log", "logging", "LOG"}

def _is_excluded(py_file: Path) -> bool:
    """Check if a file should be excluded from scanning entirely."""
    path_str = str(py_file)
    if "/tests/" in path_str or "/test/" in path_str:
        return True
    if py_file.name.startswith("test_"):
        return True
    if "__pycache__" in path_str:
        return True
    if py_file.name == "__init__.py":
        return True
    return False


def _collect_files(*scan_dirs: Path) -> List[Path]:
    """Collect non-test Python files from one or more directories."""
    python_files = []
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.rglob("*.py"):
            if _is_excluded(py_file):
                continue
            python_files.append(py_file)
    return python_files


def detect_print_calls(file_path: Path) -> List[Tuple[int, int]]:
    """
    Use AST to detect print() calls in a file.

    Args:
        file_path: Path to Python file to analyze.

    Returns:
        List of (line_number, column_offset) tuples for each print() call.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                violations.append((node.lineno, node.col_offset))
    return violations


def detect_bare_log_calls(file_path: Path) -> List[Tuple[int, int, str]]:
    """
    Use AST to detect logger.X() calls without extra= keyword argument.

    Matches any attribute call where the method name is a standard logging
    method (info, debug, warning, error, critical, exception, log).

    Args:
        file_path: Path to Python file to analyze.

    Returns:
        List of (line_number, column_offset, method_name) tuples.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHODS:
                # Only flag calls on known logger receiver names
                receiver = node.func.value
                if isinstance(receiver, ast.Name) and receiver.id in LOGGER_RECEIVER_NAMES:
                    has_extra = any(kw.arg == "extra" for kw in node.keywords)
                    if not has_extra:
                        violations.append((node.lineno, node.col_offset, node.func.attr))
    return violations


def _rel_path(file_path: Path) -> Path:
    """Get relative path from REPO_ROOT, falling back to ATDD_PKG_DIR parent."""
    try:
        return file_path.relative_to(REPO_ROOT)
    except ValueError:
        if ATDD_PKG_DIR is not None:
            return file_path.relative_to(ATDD_PKG_DIR.parent)
        return file_path


def scan_print_in_production(repo_root: Path) -> Tuple[int, List[Violation]]:
    """Scan for print() calls in production code. Used by ratchet baseline."""
    python_dir = resolve_code_root("python", repo_root)
    python_files = _collect_files(python_dir)
    violations: List[Violation] = []
    for py_file in python_files:
        prints = detect_print_calls(py_file)
        for lineno, col in prints:
            try:
                rel = py_file.relative_to(repo_root)
            except ValueError:
                rel = py_file
            violations.append(Violation(
                rule_id=_RULE_PRINT.rule_id,
                severity=_RULE_PRINT.severity,
                location=f"{rel}:{lineno}:{col}",
                detail="print() call in production code (use logger)",
                fix_hint_ref=_RULE_PRINT.fix_hint_ref,
            ))
    return len(violations), violations


def scan_structured_logging(repo_root: Path) -> Tuple[int, List[Violation]]:
    """Scan for bare log calls. Used by ratchet baseline.

    Scans consumer product code in ``repo_root/python/``. When running inside
    the atdd source repo, also scans ``src/atdd/`` as toolkit dogfooding;
    when atdd is pip-installed in a consumer repo this dogfooding scan is
    skipped (ATDD_PKG_DIR is None) so vendored site-packages code is not
    flagged.
    """
    python_dir = resolve_code_root("python", repo_root)
    scan_dirs = [python_dir]
    if ATDD_PKG_DIR is not None:
        scan_dirs.append(ATDD_PKG_DIR)
    python_files = _collect_files(*scan_dirs)
    violations: List[Violation] = []
    for py_file in python_files:
        bare_logs = detect_bare_log_calls(py_file)
        for lineno, col, method in bare_logs:
            try:
                rel = py_file.relative_to(repo_root)
            except ValueError:
                if ATDD_PKG_DIR is not None:
                    try:
                        rel = py_file.relative_to(ATDD_PKG_DIR.parent)
                    except ValueError:
                        rel = py_file
                else:
                    rel = py_file
            violations.append(Violation(
                rule_id=_RULE_STRUCTURED.rule_id,
                severity=_RULE_STRUCTURED.severity,
                location=f"{rel}:{lineno}:{col}",
                detail=f"logger.{method}() without extra= keyword",
                fix_hint_ref=_RULE_STRUCTURED.fix_hint_ref,
            ))
    return len(violations), violations


@pytest.mark.coder
def test_no_print_in_production_code():
    """
    SPEC-CODER-LOG-0001: No print() in non-test production Python code.

    Pass/fail decided by LOGGING-PRINT-001's disposition (currently
    ``strict``: any print() in production fails CI).

    Convention: atdd/coder/conventions/logging.convention.yaml (LOG-001)
    """
    python_files = _collect_files(PYTHON_DIR)
    if not python_files:
        pytest.skip("No Python files found in python/ to validate")

    _count, violations = scan_print_in_production(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id="print_in_production",
        violations=violations,
    )


@pytest.mark.coder
def test_structured_logging_format():
    """
    SPEC-CODER-LOG-0002: Logger calls must include extra= context dict.

    Pass/fail decided by LOGGING-STRUCTURED-001's disposition
    (``suppress-and-clean``): pre-existing bare log calls carry inline
    ``# atdd:suppress(coder.logging.structured) UNTIL=<date>`` markers and
    are absorbed; new bare calls fail.

    Convention: atdd/coder/conventions/logging.convention.yaml (LOG-002)
    """
    scan_dirs = [PYTHON_DIR]
    if ATDD_PKG_DIR is not None:
        scan_dirs.append(ATDD_PKG_DIR)
    python_files = _collect_files(*scan_dirs)
    if not python_files:
        pytest.skip("No Python files found to validate")

    _count, violations = scan_structured_logging(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id="structured_logging_format",
        violations=violations,
    )
