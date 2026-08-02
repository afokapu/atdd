"""No transition gate may derive a shell command from issue-body text (#1683).

The ``REFACTOR -> COMPLETE`` gate used to parse a markdown table out of the issue body
and run each cell via ``subprocess.run(..., shell=True)``. Two things went wrong, and
only the first was visible:

1. A cell written the ordinary way -- ``` `pytest src/...` (full directory) ``` -- was
   trimmed with ``str.strip("`")``, which only removes backticks from the *ends*. The
   trailing ``)`` meant the closing backtick survived mid-string, so ``sh`` waited for a
   backquote substitution that never closed and died before running anything.

2. The gate returned True when no table was found. So an issue documenting how it is
   validated was held to executing that prose, while an issue documenting nothing passed
   for free. The incentive ran backwards.

Both are gone. This test keeps them gone: it is a source-level guard, because a
behavioural test would have to reintroduce the parser to have something to assert
against.

Run: atdd validate coach
"""

import ast
from pathlib import Path

import pytest

import atdd

pytestmark = [pytest.mark.platform]

# Package-relative, not repo-relative: 'src/atdd' does not exist once atdd is installed
# as a package, and hardcoding it is what test_no_hardcoded_toolkit_root exists to stop.
ISSUE_PY = Path(atdd.__file__).resolve().parent / "coach" / "commands" / "issue.py"

# The names that implemented the removed behaviour. Their reappearance in the
# transition path is the regression this guards.
_REMOVED = {"_parse_gate_tests", "_gate_row", "_run_gate_tests", "_gate_tests"}


def test_gate_test_parser_and_runner_stay_deleted():
    """SPEC-GATE-0004: the issue-body gate-test machinery is not reintroduced.

    Given: the COMPLETE gate in issue.py
    When:  its function definitions are enumerated
    Then:  none of the removed gate-test parser/runner names is defined
    """
    tree = ast.parse(ISSUE_PY.read_text())
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    reintroduced = sorted(_REMOVED & defined)
    assert not reintroduced, (
        f"{ISSUE_PY.name} re-defines removed gate-test machinery: {reintroduced}. "
        "These parsed shell commands out of issue-body markdown and executed them "
        "(#1683). The required validate-gate status check already covers this ground; "
        "if a COMPLETE gate genuinely needs to run something, it must come from a "
        "declared, verified source -- never from prose."
    )


def test_complete_gate_does_not_consume_the_issue_body_for_execution():
    """SPEC-GATE-0005: _gate_complete does not route issue_body into a shell.

    Given: the _gate_complete method
    When:  its calls are inspected
    Then:  no call both receives issue_body and belongs to the removed runner family
    """
    tree = ast.parse(ISSUE_PY.read_text())
    gate_complete = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_gate_complete"
        ),
        None,
    )
    assert gate_complete is not None, "_gate_complete not found in issue.py"

    called = {
        node.func.attr
        for node in ast.walk(gate_complete)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    leaked = sorted(_REMOVED & called)
    assert not leaked, (
        f"_gate_complete calls removed gate-test machinery: {leaked} (#1683)."
    )
