# URN: test:drive-state-machine:record-agent-session-identity:D003-UNIT-004-no-core-path-reads-cmux
# Acceptance: acc:drive-state-machine:D003-UNIT-004-no-core-path-reads-cmux
# WMBT: wmbt:drive-state-machine:D003
# Phase: RED
# Harness: unit
# Layer: integration
"""D003-UNIT-004 — no core capture path reads or invokes a multiplexer.

Issue #1540, success criterion 10; #1480/#1483 are actively pruning cmux out of
core and this must not add to it.

Two deliberate choices in how this is checked:

STRUCTURAL, not a text grep. This file's own prose names cmux while explaining
why the module refuses to depend on it, and a prose mention is not a code path.
A regex would flag the comment and still miss `subprocess.run([resolved_name])`
— failing on the harmless case and passing the real one.

An ALLOWLIST, not a cmux blocklist. Criterion 10 names cmux, but forbidding the
string `cmux` would let core import tmux, zellij, or any multiplexer not yet
written, under a test claiming core reaches no provider. So the guard asserts
what core MAY import (stdlib + yaml + the store seam) and that it shells out
nowhere. cmux fails that as a consequence, not as a special case — and the
allowlist is itself constrained, so the guard cannot be satisfied by widening
it until the violation fits.

Fails until the capture modules exist and are clean (GREEN).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atdd.state import agent_session

pytestmark = [pytest.mark.platform]

# The guard is an ALLOWLIST, not a cmux blocklist — deliberately.
#
# Success criterion 10 names cmux, but "forbid the string cmux" would pass a
# core path that imported tmux, zellij, wezterm, or any multiplexer not yet
# written, while wearing the name of a test that claims otherwise. The real
# constraint is that core CANNOT REACH ANY PROVIDER: identity comes from
# ambient env and nothing else. A closed allowlist enforces that, and forbids
# cmux as a consequence rather than as a special case.
ALLOWED_IMPORT_ROOTS = frozenset({
    "__future__", "dataclasses", "functools", "os", "pathlib", "typing", "yaml",
})
# Relative imports inside atdd.state are the store seam itself.
ALLOWED_RELATIVE = frozenset({"store"})

# Attribute chains that shell out. Blocking imports is not enough on its own:
# `os` is legitimately needed for os.environ, and os.system would otherwise be
# an open door to invoking any provider binary.
FORBIDDEN_CALLS = frozenset({
    "system", "popen", "execv", "execve", "execvp", "spawnv", "spawnl", "which",
})

# Every core module that participates in session capture. Kept explicit rather
# than globbed so that adding a capture path without listing it here is a
# reviewable omission, not a silent gap.
CAPTURE_MODULES = (agent_session,)


def _imported_names(tree: ast.AST) -> set[str]:
    """Every imported module, as written. Relative imports keep a leading dot."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
    return names


def _disallowed_imports(tree: ast.AST) -> set[str]:
    """Imports outside the allowlist — i.e. anything that could reach a provider."""
    bad = set()
    for name in _imported_names(tree):
        if name.startswith("."):
            if name.lstrip(".") not in ALLOWED_RELATIVE:
                bad.add(name)
        elif name.split(".")[0] not in ALLOWED_IMPORT_ROOTS:
            bad.add(name)
    return bad


def _exec_calls(tree: ast.AST) -> set[str]:
    """Attribute calls that shell out to an external binary."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALLS:
                found.add(func.attr)
            elif isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                found.add(func.id)
    return found


@pytest.mark.parametrize("module", CAPTURE_MODULES, ids=lambda m: m.__name__)
def test_d003_unit_004_no_core_path_reads_cmux(module):
    """Core capture reaches no provider — cmux included, by consequence."""
    tree = ast.parse(Path(module.__file__).read_text())

    assert not _disallowed_imports(tree), (
        f"{module.__name__} imports outside the allowlist: {_disallowed_imports(tree)}"
    )
    assert not _exec_calls(tree), (
        f"{module.__name__} shells out via: {_exec_calls(tree)}"
    )


def test_d003_unit_004_the_allowlist_itself_stays_minimal():
    """Constrain the DECLARED set, not just conformance to it.

    Without this, the guard is trivially satisfiable by widening the allowlist
    until the violation fits — the assertion above would stay green while the
    property it protects quietly died.
    """
    assert "subprocess" not in ALLOWED_IMPORT_ROOTS
    assert "shutil" not in ALLOWED_IMPORT_ROOTS
    # nothing provider-shaped may be declared allowable
    for root in ALLOWED_IMPORT_ROOTS:
        assert root in {
            "__future__", "dataclasses", "functools", "os", "pathlib", "typing", "yaml",
        }, f"allowlist widened to admit {root!r}"


def test_d003_unit_004_guard_fails_on_a_planted_violation():
    """A guard that cannot fail is a stub. Fault-inject every arm."""
    # a named multiplexer
    assert _disallowed_imports(ast.parse("import cmux.client\n")) == {"cmux.client"}
    # a DIFFERENT multiplexer — the case a cmux blocklist would have missed
    assert _disallowed_imports(ast.parse("import libtmux\n")) == {"libtmux"}
    # an arbitrary provider SDK
    assert _disallowed_imports(ast.parse("from zellij import api\n")) == {"zellij"}
    # shelling out, with no import at all
    assert _exec_calls(ast.parse("os.system('cmux events')\n")) == {"system"}
    assert _exec_calls(ast.parse("shutil.which('tmux')\n")) == {"which"}


def test_d003_unit_004_guard_admits_the_legitimate_shape():
    """And it must NOT fire on what the module legitimately needs."""
    clean = ast.parse("import os\nimport yaml\nfrom .store import StateStore\n")
    assert _disallowed_imports(clean) == set()
    assert _exec_calls(ast.parse("os.environ.get('X')\n")) == set()
