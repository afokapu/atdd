"""
Regression validator: detect Phase:RED test files missing a platform guard.

A test file that declares 'Phase: RED' in its module docstring is an
intentionally-failing test targeting ATDD's own unshipped work. Such a
file MUST have @pytest.mark.platform on every test function so that the
consumer-mode 'not platform' marker exclusion prevents it from running in
consumer repos.

Usage::

    from atdd.coach.validators.red_phase_leak_scanner import scan_for_red_phase_leaks

    violations = scan_for_red_phase_leaks(Path("src/atdd/planner/validators"))
    if violations:
        sys.exit(1)

See: wmbt:govern-lifecycle:E025 (#846)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


_PHASE_RED_PATTERN = re.compile(r"Phase\s*:\s*RED", re.IGNORECASE)
_PLATFORM_MARK = "pytest.mark.platform"


def scan_for_red_phase_leaks(validator_dir: Path) -> list[str]:
    """
    Scan *validator_dir* for test files that declare 'Phase: RED' without
    a @pytest.mark.platform guard on every test function.

    Returns a list of human-readable violation strings (empty = clean).

    A file is checked only when:
      - its name starts with ``test_``
      - its module-level docstring (first AST node) contains 'Phase: RED'

    A file is considered *clean* when every top-level function whose name
    starts with ``test_`` has at least one decorator that resolves to the
    ``pytest.mark.platform`` attribute expression.
    """
    violations: list[str] = []

    for path in sorted(validator_dir.rglob("test_*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue

        if not _PHASE_RED_PATTERN.search(source):
            continue

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        # Only flag if the module docstring contains 'Phase: RED'
        if not _module_docstring_has_phase_red(tree):
            continue

        unguarded = _unguarded_test_functions(tree)
        if unguarded:
            violations.append(
                f"{path}: Phase:RED file missing @pytest.mark.platform on: "
                + ", ".join(unguarded)
            )

    return violations


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _module_docstring_has_phase_red(tree: ast.Module) -> bool:
    """Return True when the module's first statement is a 'Phase: RED' docstring."""
    if not tree.body:
        return False
    first = tree.body[0]
    if not isinstance(first, ast.Expr):
        return False
    value = first.value
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        return False
    return bool(_PHASE_RED_PATTERN.search(value.value))


def _module_has_pytestmark_platform(tree: ast.Module) -> bool:
    """
    Return True when the module has a module-level pytestmark that includes
    pytest.mark.platform, e.g. ``pytestmark = [pytest.mark.platform]`` or
    ``pytestmark = pytest.mark.platform``.

    This is the standard module-wide guard; when present, every test in the
    file inherits the mark and individual per-function decorators are not needed.
    """
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "pytestmark":
                return _expr_contains_platform_mark(node.value)
    return False


def _expr_contains_platform_mark(node: ast.expr) -> bool:
    """Return True when an expression is or contains pytest.mark.platform."""
    if _decorator_is_platform_mark(node):
        return True
    if isinstance(node, (ast.List, ast.Tuple)):
        return any(_decorator_is_platform_mark(elt) for elt in node.elts)
    return False


def _unguarded_test_functions(tree: ast.Module) -> list[str]:
    """
    Return the names of top-level test functions that lack a platform guard.

    A function is considered guarded when:
      - it has @pytest.mark.platform on its own decorator list, OR
      - the module has a module-level ``pytestmark`` that includes
        ``pytest.mark.platform`` (which applies the mark to all tests).
    """
    if _module_has_pytestmark_platform(tree):
        return []

    unguarded: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        if not _has_platform_mark(node):
            unguarded.append(node.name)
    return unguarded


def _has_platform_mark(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True when the function has @pytest.mark.platform."""
    for decorator in func_node.decorator_list:
        if _decorator_is_platform_mark(decorator):
            return True
    return False


def _decorator_is_platform_mark(node: ast.expr) -> bool:
    """
    Match @pytest.mark.platform as an ast.Attribute chain.

    Handles both:
      @pytest.mark.platform          (ast.Attribute on ast.Attribute on ast.Name)
      @pytest.mark.platform()        (ast.Call wrapping the above)
    """
    if isinstance(node, ast.Call):
        node = node.func
    if not isinstance(node, ast.Attribute):
        return False
    if node.attr != "platform":
        return False
    parent = node.value
    if not isinstance(parent, ast.Attribute):
        return False
    if parent.attr != "mark":
        return False
    grandparent = parent.value
    if not isinstance(grandparent, ast.Name):
        return False
    return grandparent.id == "pytest"
