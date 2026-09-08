# URN: test:enforce-conventions-ci:enforce-conventions-ci:E004-UNIT-002-a-new-type-error-fails-while-baselined-debt-does-not
# Acceptance: acc:enforce-conventions-ci:E004-UNIT-002-a-new-type-error-fails-while-baselined-debt-does-not
# WMBT: wmbt:enforce-conventions-ci:E004
# Phase: RED
# Layer: application
"""E004-UNIT-002 — an unrunnable tool refuses; it does not pass.

The failure mode this guards is the one every defect fixed in this session
shared: something passing because the check it faced could not fail on it. A
gate that silently skips when its tool is absent reports green over an
observation it never made.
"""
from __future__ import annotations

import pytest

from atdd.coder.validators._static_ratchet import (
    Finding,
    ToolUnavailable,
    finding_identity,
    new_findings,
    resolve_tool,
)


def test_an_absent_tool_raises_rather_than_returning_no_findings():
    with pytest.raises(ToolUnavailable) as exc:
        resolve_tool("definitely-not-a-real-tool-xyz")

    assert "definitely-not-a-real-tool-xyz" in str(exc.value), (
        "the refusal must name the tool, or an operator cannot act on it"
    )
    assert "install" in str(exc.value).lower(), (
        "a refusal that does not say how to fix it is barely better than the "
        "vacuous pass it replaces"
    )


def test_a_resolvable_tool_returns_an_invocation():
    argv = resolve_tool("python3")
    assert argv and argv[0], "a tool on PATH must resolve to something runnable"


def test_the_type_ratchet_shares_the_lint_semantics():
    """Both gates are the same ratchet over different finding sources."""
    known = Finding(path="a.py", rule="reportOptionalMemberAccess", line=3,
                    message="x is not a known attribute of None")
    fresh = Finding(path="b.py", rule="reportArgumentType", line=9, message="…")

    assert new_findings([known, fresh], {finding_identity(known)}) == [fresh]


def test_the_type_checker_is_pinned_to_the_running_interpreter():
    """A baseline is only frozen if the analysis environment is.

    Measured on this tree: pyright reports 575 errors against the environment
    carrying the project's dependencies and 647 against a bare one — same source,
    different interpreter found on PATH. Without the pin, a baseline frozen under
    one environment fails under the other for a reason no commit caused.
    """
    import sys

    from atdd.coder.validators._static_ratchet import pyright_argv

    argv = pyright_argv()
    assert "--pythonpath" in argv, (
        "pyright must be pinned to an interpreter; left to itself it picks one off "
        "PATH and the frozen baseline stops describing the tree"
    )
    assert argv[argv.index("--pythonpath") + 1] == sys.executable, (
        "the pin must be the interpreter running this process — the environment the "
        "analysed code actually imports from"
    )
