# URN: test:review-phase-boundaries:phase-boundary-review:E004-UNIT-002-suite-audit-finds-no-live-multiplexer-callers
# Acceptance: acc:review-phase-boundaries:E004-UNIT-002-suite-audit-finds-no-live-multiplexer-callers
# WMBT: wmbt:review-phase-boundaries:E004
# Phase: RED
# Layer: assembly
# Runtime: python
# Assertion: structural
# Purpose: A static audit over the coach test suite finds zero tests that invoke the real coach against a live multiplexer (no --dry-run, no injected stub)
"""RED Test for test:review-phase-boundaries:phase-boundary-review:E004-UNIT-002-suite-audit-finds-no-live-multiplexer-callers
wagon: review-phase-boundaries | feature: phase-boundary-review | phase: RED
WMBT: wmbt:review-phase-boundaries:E004

Purpose
-------
A regression guard: an AST scanner walks every test file under
``src/atdd/coach/commands/tests/`` and ``src/atdd/coach/handlers/tests/`` and
flags any call to ``run_cli`` / ``coach.run_cli`` made with a bare issue number
(``["358"]``) that is NOT hermetic — i.e. the call has no ``--dry-run`` in its
argument list AND the enclosing function injects no stub multiplexer
(no ``_resolve_multiplexer`` monkeypatch, no ``FakeMultiplexer``).

Such a call invokes the real coach, which spawns and leaks a real cmux
workspace. The scanner reports ``file:line`` for each offender so a future
regression is pinpointed.

RED-first: before the hermeticity fix the scanner flags
``test_e002_integration_001_cli_dispatch_routes_review.py:72``
(``coach.run_cli(["358"])``) → this test FAILS. After the fix that call carries
``--dry-run`` (or a stub multiplexer) → the scanner returns an empty list →
this test PASSES.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# tests/ → commands|handlers/ → coach/ → atdd/ → src/ → repo root
_REPO_ROOT = Path(__file__).resolve().parents[5]

_AUDITED_TEST_DIRS = (
    "src/atdd/coach/commands/tests",
    "src/atdd/coach/handlers/tests",
)

# Markers that prove a stub multiplexer is in scope for a test function.
_STUB_MULTIPLEXER_MARKERS = (
    "_resolve_multiplexer",  # monkeypatch.setattr(..., "_resolve_multiplexer", ...)
    "FakeMultiplexer",
    "SpyMultiplexer",
)


def _is_run_cli_call(call: ast.Call) -> bool:
    """True when ``call`` targets ``run_cli`` (bare) or ``<obj>.run_cli``."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == "run_cli"
    if isinstance(func, ast.Attribute):
        return func.attr == "run_cli"
    return False


def _argv_list(call: ast.Call):
    """Return the first positional list-literal argument, or None."""
    for arg in call.args:
        if isinstance(arg, ast.List):
            return arg
    return None


def _string_constants(node: ast.AST) -> list[str]:
    return [
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def _call_has_bare_issue_number(call: ast.Call) -> bool:
    """True when the argv list literal contains an all-digit string element."""
    argv = _argv_list(call)
    if argv is None:
        return False
    return any(
        isinstance(el, ast.Constant)
        and isinstance(el.value, str)
        and el.value.isdigit()
        for el in argv.elts
    )


def _call_has_dry_run(call: ast.Call) -> bool:
    """True when the argv list literal contains the ``--dry-run`` flag."""
    argv = _argv_list(call)
    if argv is None:
        return False
    return any(
        isinstance(el, ast.Constant) and el.value == "--dry-run"
        for el in argv.elts
    )


def _func_has_stub_multiplexer(func: ast.AST) -> bool:
    """True when the enclosing function references a stub-multiplexer marker."""
    names = {
        n.id for n in ast.walk(func) if isinstance(n, ast.Name)
    } | {
        n.attr for n in ast.walk(func) if isinstance(n, ast.Attribute)
    }
    strings = set(_string_constants(func))
    return any(
        marker in names or marker in strings
        for marker in _STUB_MULTIPLEXER_MARKERS
    )


def _find_non_hermetic_run_cli_call_sites() -> list[str]:
    """Scan the audited test dirs; return ``file:line`` for each leak site."""
    offenders: set[str] = set()
    for rel_dir in _AUDITED_TEST_DIRS:
        audit_dir = _REPO_ROOT / rel_dir
        if not audit_dir.is_dir():
            continue
        for path in sorted(audit_dir.rglob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for func in ast.walk(tree):
                if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                has_stub = _func_has_stub_multiplexer(func)
                for call in ast.walk(func):
                    if not isinstance(call, ast.Call):
                        continue
                    if not _is_run_cli_call(call):
                        continue
                    if not _call_has_bare_issue_number(call):
                        continue
                    if _call_has_dry_run(call):
                        continue
                    if has_stub:
                        continue
                    rel = path.relative_to(_REPO_ROOT)
                    offenders.add(f"{rel}:{call.lineno}")
    return sorted(offenders)


def test_audited_test_dirs_exist():
    """The directories the audit scans must be present."""
    for rel_dir in _AUDITED_TEST_DIRS:
        assert (_REPO_ROOT / rel_dir).is_dir(), (
            f"Audited coach test directory not found: {rel_dir}"
        )


def test_no_coach_test_invokes_real_coach_against_live_multiplexer():
    """Every run_cli(['<issue>']) call in the coach test suite must be hermetic."""
    offenders = _find_non_hermetic_run_cli_call_sites()
    assert offenders == [], (
        "Coach test(s) invoke the real coach with a bare issue number and "
        "neither --dry-run nor an injected stub multiplexer — each such call "
        "spawns and leaks a real cmux workspace + observer:\n  "
        + "\n  ".join(offenders)
        + "\nMake each call hermetic: add '--dry-run' for routing-only tests, "
        "or inject a stub multiplexer for tests that exercise spawn logic."
    )
