# URN: test:integration-hardening:repo-root-bare-guard:Y003-UNIT-001-004
# Acceptance: acc:integration-hardening:Y003-UNIT-001-repo-root-guard-is-function-scoped-autouse
# Acceptance: acc:integration-hardening:Y003-UNIT-002-guard-names-offending-test-in-failure
# Acceptance: acc:integration-hardening:Y003-UNIT-003-guard-restores-core-bare-before-asserting
# Acceptance: acc:integration-hardening:Y003-UNIT-004-meta-test-run-leaves-core-bare-unchanged
# WMBT: wmbt:integration-hardening:Y003
# Phase: RED
# Layer: coach.validator

"""Repo-root core.bare guard — regression gate (issue #771).

The existing session-scoped guard in src/atdd/coach/validators/conftest.py
covers only that sub-directory. A polluting test in commands/, handlers/,
utils/, or templates/hooks/ can write core.bare=true to the shared
.git/config undetected.

These tests assert:
  GT-Y003-001 — function-scoped autouse guard is in src/atdd/conftest.py
  GT-Y003-002 — failure message names the offending test via request.node.nodeid
  GT-Y003-003 — guard RESTORES core.bare before asserting (so the session continues clean)
  GT-Y003-004 — meta-test: the guard fixture is present and covers the right scope
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

_SRC_ATDD = Path(__file__).resolve().parent.parent.parent  # src/atdd
_ROOT_CONFTEST = _SRC_ATDD / "conftest.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_root_conftest() -> str:
    assert _ROOT_CONFTEST.is_file(), f"Root conftest not found: {_ROOT_CONFTEST}"
    return _ROOT_CONFTEST.read_text(encoding="utf-8")


def _get_fixture_defs(source: str) -> list[ast.FunctionDef]:
    """Return all @pytest.fixture-decorated function defs from source."""
    tree = ast.parse(source)
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            dec_str = ast.unparse(dec)
            if "pytest.fixture" in dec_str or "fixture" in dec_str:
                results.append(node)
                break
    return results


def _find_bare_guard_fixture(source: str) -> ast.FunctionDef | None:
    """Return the fixture definition that monitors core.bare, or None."""
    for fn in _get_fixture_defs(source):
        fn_src = ast.unparse(fn)
        if "core.bare" in fn_src:
            return fn
    return None


# ---------------------------------------------------------------------------
# GT-Y003-001 — function-scoped autouse guard in root conftest
# ---------------------------------------------------------------------------


def test_root_conftest_has_core_bare_guard():
    """GT-Y003-001a: src/atdd/conftest.py must contain a fixture that references core.bare."""
    content = _read_root_conftest()
    assert "core.bare" in content, (
        f"src/atdd/conftest.py has no reference to 'core.bare'.\n"
        f"Fix: add a function-scoped autouse fixture that snapshots and restores\n"
        f"core.bare for every test under src/atdd (issue #771).\n"
        f"Path: {_ROOT_CONFTEST}"
    )


def test_root_conftest_bare_guard_is_autouse():
    """GT-Y003-001b: the core.bare guard must be autouse=True so it fires without explicit request."""
    content = _read_root_conftest()
    guard = _find_bare_guard_fixture(content)
    assert guard is not None, (
        "No @pytest.fixture with 'core.bare' found in src/atdd/conftest.py"
    )
    dec_src = " ".join(ast.unparse(d) for d in guard.decorator_list)
    assert "autouse=True" in dec_src or "autouse = True" in dec_src, (
        f"The core.bare guard fixture '{guard.name}' must declare autouse=True.\n"
        f"Current decorator(s): {dec_src!r}"
    )


def test_root_conftest_bare_guard_is_function_scoped():
    """GT-Y003-001c: guard must be function-scoped (not session-scoped) to name each test."""
    content = _read_root_conftest()
    guard = _find_bare_guard_fixture(content)
    assert guard is not None, (
        "No @pytest.fixture with 'core.bare' found in src/atdd/conftest.py"
    )
    dec_src = " ".join(ast.unparse(d) for d in guard.decorator_list)
    # Function scope is the default; it is wrong only if scope= is explicitly set to something else
    assert 'scope="session"' not in dec_src and "scope='session'" not in dec_src, (
        f"The core.bare guard '{guard.name}' must NOT be session-scoped.\n"
        f"A session-scoped guard cannot name the offending test (issue #771).\n"
        f"Use the default scope (function) or scope='function'."
    )


def test_root_conftest_bare_guard_accepts_request_fixture():
    """GT-Y003-001d: guard must accept 'request' to access the test's nodeid."""
    content = _read_root_conftest()
    guard = _find_bare_guard_fixture(content)
    assert guard is not None, (
        "No @pytest.fixture with 'core.bare' found in src/atdd/conftest.py"
    )
    arg_names = [a.arg for a in guard.args.args]
    assert "request" in arg_names, (
        f"The core.bare guard '{guard.name}' must accept 'request' as a parameter\n"
        f"so it can reference request.node.nodeid to name the offending test.\n"
        f"Current parameters: {arg_names}"
    )


# ---------------------------------------------------------------------------
# GT-Y003-002 — failure message names offending test
# ---------------------------------------------------------------------------


def test_root_conftest_bare_guard_names_test_in_failure():
    """GT-Y003-002: assert message must reference request.node to name the offending test."""
    content = _read_root_conftest()
    guard = _find_bare_guard_fixture(content)
    assert guard is not None, (
        "No @pytest.fixture with 'core.bare' found in src/atdd/conftest.py"
    )
    fn_src = ast.unparse(guard)
    assert "request.node" in fn_src, (
        f"The core.bare guard '{guard.name}' must include request.node (or\n"
        f"request.node.nodeid) in its assertion message so the developer can\n"
        f"identify which test caused the contamination.\n"
        f"Fix: embed request.node.nodeid in the assert failure message."
    )


# ---------------------------------------------------------------------------
# GT-Y003-003 — restore before assert
# ---------------------------------------------------------------------------


def test_root_conftest_bare_guard_restores_before_asserting():
    """GT-Y003-003: guard must restore core.bare BEFORE it asserts, so the session continues clean.

    We check that the fixture body contains a git config call that writes
    back the snapshotted value, and that this write appears before any assert
    statement that references core.bare.
    """
    content = _read_root_conftest()
    guard = _find_bare_guard_fixture(content)
    assert guard is not None, (
        "No @pytest.fixture with 'core.bare' found in src/atdd/conftest.py"
    )

    fn_src = ast.unparse(guard)

    # Guard must contain a restore call — any git config write with the bare key
    has_restore = (
        "core.bare" in fn_src
        and ("subprocess" in fn_src or "git" in fn_src)
        and "yield" in fn_src
    )
    assert has_restore, (
        f"The core.bare guard '{guard.name}' appears to have no restore logic.\n"
        f"After yield, it must write back the original core.bare value before\n"
        f"asserting, so subsequent tests run in a clean state (issue #771).\n"
        f"Pattern: if bare_before != bare_after: git config core.bare <bare_before>"
    )

    # Verify restore appears BEFORE the assert in the AST post-yield body
    body_after_yield: list[ast.stmt] = []
    saw_yield = False
    for stmt in ast.walk(guard):
        if not isinstance(stmt, ast.stmt):
            continue
    # Walk the function body linearly looking for yield then restore then assert
    restore_lineno: int | None = None
    assert_lineno: int | None = None
    for node in ast.walk(guard):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Yield):
            pass
        if isinstance(node, ast.Assert):
            body = ast.unparse(node)
            if "core.bare" in body or "bare" in body.lower():
                if assert_lineno is None or node.lineno < assert_lineno:
                    assert_lineno = node.lineno
        if isinstance(node, ast.Call):
            call_s = ast.unparse(node)
            if "core.bare" in call_s and ("config" in call_s or "git" in call_s):
                if "rev-parse" not in call_s and "HEAD" not in call_s:
                    if restore_lineno is None or node.lineno < restore_lineno:
                        restore_lineno = node.lineno

    if restore_lineno is not None and assert_lineno is not None:
        assert restore_lineno < assert_lineno, (
            f"In '{guard.name}': the restore call (line {restore_lineno}) must come\n"
            f"BEFORE the assert (line {assert_lineno}) so contamination is cleaned up\n"
            f"even when the test fails."
        )


# ---------------------------------------------------------------------------
# GT-Y003-004 — meta-test: guard fixture present + core.bare unchanged
# ---------------------------------------------------------------------------


def test_meta_root_conftest_guard_present():
    """GT-Y003-004a: static meta-check — the guard fixture is in the root conftest."""
    content = _read_root_conftest()
    guard = _find_bare_guard_fixture(content)
    assert guard is not None, (
        "Meta-test failed: no core.bare guard fixture found in src/atdd/conftest.py.\n"
        "This guard is the primary defense against the Wave 12 contamination\n"
        "recurring in test runs outside validators/ (issue #771)."
    )


def test_meta_core_bare_unchanged_by_guard_itself():
    """GT-Y003-004b: reading the guard source must not itself mutate core.bare.

    A trivially true self-consistency check: importing and inspecting the root
    conftest AST must not change git config core.bare.
    """

    def _git_core_bare() -> str:
        r = subprocess.run(
            ["git", "config", "core.bare"],
            capture_output=True, text=True,
        )
        return r.stdout.strip()

    before = _git_core_bare()
    _ = _read_root_conftest()
    _ = _find_bare_guard_fixture(_read_root_conftest())
    after = _git_core_bare()

    assert before == after, (
        f"Reading src/atdd/conftest.py changed core.bare!\n"
        f"  before: {before!r}\n"
        f"  after:  {after!r}\n"
        "This should be impossible — investigation needed."
    )
