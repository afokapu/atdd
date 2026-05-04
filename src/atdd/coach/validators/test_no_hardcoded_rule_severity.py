# URN: component:govern-lifecycle:enforcement-substrate:test_no_hardcoded_rule_severity:backend:domain
# Runtime: python
# Purpose: Forbid migrated validators from re-introducing RULE_SEVERITY constants or severity=<literal> on Violation(...) calls.

"""Drift guard for the bind_rule migration (issue #388).

Once a validator imports ``atdd.coach.utils.rule_binding.bind_rule``, its
severity, description, and recipe come from the convention.  Re-declaring
``RULE_SEVERITY = 4`` (or duplicating the integer literal in
``Violation(severity=4, ...)`` calls) would re-open the drift class the
binding helper exists to close.

This validator AST-walks every Python file under
``src/atdd/{coach,coder}/validators/`` and, for the subset that imports
``bind_rule`` (or the module), rejects:

1. Module-scope ``*_RULE_SEVERITY = <int>`` assignments (e.g.
   ``RULE_SEVERITY = 4``, ``XSS_RULE_SEVERITY = 5``).
2. ``Violation(...)`` calls whose ``severity=`` keyword argument is a bare
   integer literal — should be ``_RULE.severity`` instead.

Fixtures, tests outside the validators/ tree, and validators that have not
yet adopted ``bind_rule`` are out of scope (they're tracked in #389).

Convention: ``src/atdd/coach/conventions/rule-id.convention.yaml``
            (rule ``coach.rule-id.no-hardcoded-rule-severity``).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List

import pytest

import atdd
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation


# ---------------------------------------------------------------------------
# Path constants & rule binding
# ---------------------------------------------------------------------------
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
VALIDATOR_ROOTS = [
    ATDD_PKG_DIR / "coach" / "validators",
    ATDD_PKG_DIR / "coder" / "validators",
]

_RULE = bind_rule("coach.rule-id.no-hardcoded-rule-severity")

_BIND_RULE_MODULE = "atdd.coach.utils.rule_binding"


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------
def _is_excluded(py_file: Path) -> bool:
    """Files we never scan."""
    parts = set(py_file.parts)
    if "fixtures" in parts:
        return True
    if "__pycache__" in parts:
        return True
    if py_file.name in {"__init__.py", "conftest.py"}:
        return True
    return False


def _collect_validator_files() -> List[Path]:
    out: List[Path] = []
    for root in VALIDATOR_ROOTS:
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            if _is_excluded(py):
                continue
            out.append(py)
    return out


# ---------------------------------------------------------------------------
# AST queries
# ---------------------------------------------------------------------------
def _imports_bind_rule(tree: ast.AST) -> bool:
    """``True`` when the module imports bind_rule (or the helper module)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == _BIND_RULE_MODULE:
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _BIND_RULE_MODULE:
                    return True
    return False


def _module_scope_severity_constants(tree: ast.Module) -> List[ast.Assign]:
    """Module-scope ``<NAME>_RULE_SEVERITY = <int>`` (or ``RULE_SEVERITY``)."""
    out: List[ast.Assign] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if not isinstance(stmt.value, ast.Constant) or not isinstance(
            stmt.value.value, int
        ) or isinstance(stmt.value.value, bool):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and (
                target.id == "RULE_SEVERITY" or target.id.endswith("_RULE_SEVERITY")
            ):
                out.append(stmt)
                break
    return out


def _violation_calls_with_literal_severity(tree: ast.AST) -> List[ast.Call]:
    """``Violation(..., severity=<int-literal>, ...)`` call sites."""
    out: List[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            continue
        if name != "Violation":
            continue
        for kw in node.keywords:
            if kw.arg != "severity":
                continue
            if (
                isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, int)
                and not isinstance(kw.value.value, bool)
            ):
                out.append(node)
                break
    return out


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------
def _relpath(p: Path) -> str:
    try:
        return str(p.relative_to(ATDD_PKG_DIR.parent))
    except ValueError:
        return str(p)


def scan_for_hardcoded_severity() -> List[Violation]:
    """Return Violations for every drifted validator file."""
    violations: List[Violation] = []
    for py_file in _collect_validator_files():
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (OSError, SyntaxError, UnicodeDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow)
            # Unparseable files are policed by the syntax test_suite; skip.
            continue
        if not _imports_bind_rule(tree):
            continue

        rel = _relpath(py_file)

        for stmt in _module_scope_severity_constants(tree):
            target_name = next(
                t.id for t in stmt.targets if isinstance(t, ast.Name)
            )
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{rel}:{stmt.lineno}",
                    detail=(
                        f"module-scope `{target_name} = <int>` shadows "
                        f"the convention's authoritative severity. Use "
                        f"`_RULE = bind_rule(...)` then `_RULE.severity`."
                    ),
                    fix_hint_ref=_RULE.fix_hint_ref,
                )
            )

        for call in _violation_calls_with_literal_severity(tree):
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{rel}:{call.lineno}",
                    detail=(
                        "`Violation(severity=<int>)` duplicates the "
                        "convention. Pass `_RULE.severity` instead."
                    ),
                    fix_hint_ref=_RULE.fix_hint_ref,
                )
            )

    return violations


# ===========================================================================
# Test
# ===========================================================================
@pytest.mark.coach
def test_no_hardcoded_rule_severity_in_migrated_validators():
    """Migrated validators must not redeclare rule severity.

    SPEC: ``rule-id.convention.yaml::rules[coach.rule-id.no-hardcoded-rule-severity]``.

    Given:  Python files under ``src/atdd/{coach,coder}/validators/`` that
            import ``atdd.coach.utils.rule_binding``.
    When:   AST scan looks for module-scope ``*_RULE_SEVERITY = <int>``
            assignments and ``Violation(severity=<int-literal>)`` kwargs.
    Then:   No such occurrences exist — severity comes from the convention
            via ``_RULE.severity``.
    """
    violations = scan_for_hardcoded_severity()
    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} hardcoded-severity violation(s) "
            f"in validators that import bind_rule:\n\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
