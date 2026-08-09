# URN: test:govern-lifecycle:enforcement-substrate:self-skip-matcher-parity:backend:tests
# Runtime: python
# Purpose: #1740 Phase 1 — core's self-skip matcher table and the python-pytest workspace kernel's must not drift apart.

"""Parity between core's self-skip matcher table and the workspace kernel's.

**Why this test exists instead of a shared import.** Core and the python-pytest
workspace each match the same self-skip mechanisms. The obvious de-duplication —
have core import the workspace kernel — is not available:

  * core imports no detector code (the placement verdict on ``#1740``);
  * ``.atdd/workspaces/`` is digest-pinned **installed substrate** that a
    consumer repo may not have installed, may have at another version, or may
    have disabled, so a core validator importing it would break there;
  * there is no ``__init__.py`` anywhere under ``.atdd/workspaces`` — it is not
    an importable package — and core deliberately PRUNES ``.atdd`` when walking
    (``test_repo_validator_binding.py``, ``test_smoke_no_collaborator_substitution.py``);
  * the sanctioned core->detector channel is the provider **subprocess**
    boundary (``atdd.enforce.runner``), never an import.

So core keeps its own table, and this test holds the two to being identical by
reading the kernel as **text** and AST-parsing its literal — no import, no
execution of detector code. Drift becomes a red test rather than a silent
behavioural split.

**What this does NOT assert.** Not that the two callers report the same
*mechanism* for a given file: they deliberately differ. Core selects the first
match in TABLE order; the workspace selects the first in SOURCE order. That
divergence predates ``#1740`` and is preserved by it, pinned on the workspace
side by ``test_self_skip_kernel.py``. Only the shared fact — the matcher table —
is asserted equal here.

Toolkit dogfood: reads toolkit-only repo state (the ``platform`` marker, #1475).
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Tuple

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.tester.validators.test_live_smoke_execution import _SELF_SKIP_PATTERNS


pytestmark = [pytest.mark.platform]

_KERNEL_RELPATH = Path(
    ".atdd/workspaces/atdd.workspace.python-pytest/0.1.0/implementations"
    "/live_smoke_execution_detector/self_skip_kernel.py"
)
_TABLE_NAME = "SELF_SKIP_MATCHERS"


def _kernel_path() -> Path:
    return find_repo_root() / _KERNEL_RELPATH


def _parse_kernel_table(source: str) -> List[Tuple[str, str]]:
    """Extract ``SELF_SKIP_MATCHERS`` from kernel source by AST, without importing.

    Reads the annotated assignment's literal tuple of ``(pattern, label)`` string
    pairs. Raises ``AssertionError`` with a specific reason rather than returning
    an empty list, so a refactor that renames or restructures the table fails
    loudly instead of vacuously comparing two empties.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == _TABLE_NAME for t in targets):
            continue
        value = node.value
        assert isinstance(value, (ast.Tuple, ast.List)), (
            f"{_TABLE_NAME} must be a literal tuple/list so it can be read "
            f"without importing detector code; got {type(value).__name__}"
        )
        pairs: List[Tuple[str, str]] = []
        for element in value.elts:
            assert isinstance(element, (ast.Tuple, ast.List)) and len(element.elts) == 2, (
                f"each {_TABLE_NAME} entry must be a literal (pattern, label) pair"
            )
            pattern, label = element.elts
            assert isinstance(pattern, ast.Constant) and isinstance(label, ast.Constant), (
                f"{_TABLE_NAME} entries must be string literals, not computed values"
            )
            pairs.append((pattern.value, label.value))
        return pairs
    raise AssertionError(
        f"{_TABLE_NAME} not found in {_KERNEL_RELPATH} — the workspace kernel was "
        f"renamed, moved or deleted. Core's matcher table is now unguarded."
    )


def test_workspace_kernel_is_present() -> None:
    """The kernel exists where core expects it.

    Fail-closed on purpose: a missing kernel means core's table has no parity
    guard at all, which is exactly the silent-divergence state this test was
    added to end. It must not degrade to a skip.
    """
    path = _kernel_path()
    assert path.is_file(), (
        f"self-skip kernel not found at {_KERNEL_RELPATH}. Core's matcher table is "
        f"unguarded against drift. If the kernel moved, update _KERNEL_RELPATH."
    )


def test_core_and_workspace_matcher_tables_are_identical() -> None:
    """The shared fact — which mechanisms count as a self-skip — is one table."""
    kernel_pairs = _parse_kernel_table(_kernel_path().read_text(encoding="utf-8"))
    core_pairs = [(pattern.pattern, label) for pattern, label in _SELF_SKIP_PATTERNS]

    assert kernel_pairs == core_pairs, (
        "core and the python-pytest workspace kernel disagree about which "
        "constructs are self-skips.\n"
        f"  core   : {core_pairs}\n"
        f"  kernel : {kernel_pairs}\n"
        "Update both, in the same order — the order is load-bearing for core's "
        "table-order selection rule."
    )


def test_table_order_is_load_bearing_and_documented() -> None:
    """Core selects by table order, so a reorder is a behaviour change.

    Guards the specific mistake this parity pair invites: someone alphabetises
    one table, both still contain the same entries as sets, and core silently
    starts reporting a different mechanism.
    """
    kernel_pairs = _parse_kernel_table(_kernel_path().read_text(encoding="utf-8"))
    core_pairs = [(pattern.pattern, label) for pattern, label in _SELF_SKIP_PATTERNS]

    assert set(kernel_pairs) == set(core_pairs), "entries differ, not just order"
    assert kernel_pairs == core_pairs, (
        "the tables hold the same entries in a DIFFERENT order. Core reports the "
        "first match in table order, so reordering changes which mechanism core "
        "names for a file carrying several. Restore the shared order."
    )
