# URN: test:author-atdd-substrate:author-issue-body:C014-UNIT-003-one-bound-implementation-serves-both-enforcers
# Acceptance: acc:author-atdd-substrate:C014-UNIT-003-one-bound-implementation-serves-both-enforcers
# WMBT: wmbt:author-atdd-substrate:C014
# Phase: RED
# Layer: application
"""C014-UNIT-003 — exactly one bound implementation of the artifact policy.

There is no convention rule, so there is nothing for either enforcer to bind
to, and each invented its own policy — including the same escape. Fixing the
two implementations alone leaves them free to drift apart again; the rule is
what makes them bindable.

This is the acceptance that fails if a second copy of the ``total == 0`` escape
ever reappears in either enforcer, or if the shared checker stops binding its
rules at module-import time.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import atdd

_PKG = Path(atdd.__file__).resolve().parent

_SHARED_CHECKER = _PKG / "coach" / "utils" / "artifact_claims.py"
_RUNTIME_GATE = _PKG / "coach" / "commands" / "issue.py"
_VALIDATOR = _PKG / "coach" / "validators" / "test_issue_gate_completion.py"

# ``_RULE = bind_rule("...")`` at column 0 — module-import time, not inside a
# function where it would only fire when the code path runs.
_MODULE_LEVEL_BIND = re.compile(r"^[A-Z_][A-Z_0-9]*\s*=\s*bind_rule\(", re.MULTILINE)


def _is_artifact_total(node: ast.AST) -> bool:
    """Whether *node* computes the total over the parsed artifact groups.

    That is ``sum(len(v) for v in artifacts.values())`` however it is spelled —
    the shape both enforcers independently wrote.
    """
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
        return False
    if node.func.id != "sum" or not node.args:
        return False
    inner = node.args[0]
    if not isinstance(inner, (ast.GeneratorExp, ast.ListComp)):
        return False
    return any(
        isinstance(gen.iter, ast.Call)
        and isinstance(gen.iter.func, ast.Attribute)
        and gen.iter.func.attr == "values"
        and isinstance(gen.iter.func.value, ast.Name)
        and "artifact" in gen.iter.func.value.id
        for gen in inner.generators
    )


def _escape_branches(source: str) -> list[str]:
    """Every branch that short-circuits on the artifact total being zero.

    Structural, not textual: a docstring recounting the history is not an
    escape, and neither is counting the claims to print "Verifying N
    artifacts". What this finds is a *branch* keyed on the empty declaration —
    exactly the free pass #1726 removed, under any variable name.
    """
    tree = ast.parse(source)

    totals = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and _is_artifact_total(node.value)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    def _tests_empty(test: ast.AST) -> bool:
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            operand = test.operand
            return (isinstance(operand, ast.Name) and operand.id in totals) or _is_artifact_total(operand)
        if not (isinstance(test, ast.Compare) and len(test.ops) == 1):
            return False
        if not isinstance(test.ops[0], (ast.Eq, ast.LtE, ast.Lt)):
            return False
        left, right = test.left, test.comparators[0]
        names_total = (isinstance(left, ast.Name) and left.id in totals) or _is_artifact_total(left)
        return names_total and isinstance(right, ast.Constant) and right.value == 0

    return [
        f"line {node.lineno}: branch on an empty artifact declaration"
        for node in ast.walk(tree)
        if isinstance(node, (ast.If, ast.IfExp)) and _tests_empty(node.test)
    ]


# The escape exactly as both enforcers wrote it, kept as a positive control so
# the detector above cannot pass by failing to detect anything.
_THE_ESCAPE_AS_IT_WAS = """
def gate(artifacts):
    total = sum(len(v) for v in artifacts.values())
    if total == 0:
        return True, ["  No artifacts declared"]
    return check(artifacts)
"""


def test_c014_unit_003_the_shared_checker_binds_its_rules_at_import_time():
    from atdd.coach.utils.artifact_claims import (
        BOUND_RULES,
        RULE_CLAIMS_RESOLVE,
        RULE_MUST_BE_DECLARED,
    )

    assert set(BOUND_RULES) == {RULE_CLAIMS_RESOLVE, RULE_MUST_BE_DECLARED}, (
        "the shared checker must resolve every rule it emits through bind_rule "
        "at module-import time (SPEC-COACH-RULEID-0007)"
    )
    for rule_id, meta in BOUND_RULES.items():
        assert meta.rule_id == rule_id


def test_c014_unit_003_the_validator_binds_and_delegates():
    """The COMPLETE-gate validator calls ``bind_rule`` and owns no policy of its own."""
    source = _VALIDATOR.read_text(encoding="utf-8")

    assert _MODULE_LEVEL_BIND.search(source), (
        "test_issue_gate_completion.py calls bind_rule zero times while guarding "
        "the COMPLETE gate — CLAUDE.md requires the module-import-time binding"
    )
    assert "artifact_claims" in source, (
        "the validator must delegate to the shared checker, not carry its own copy"
    )


def test_c014_unit_003_the_escape_detector_detects_the_escape():
    """Positive control: the detector recognises the free pass as it was written."""
    assert _escape_branches(_THE_ESCAPE_AS_IT_WAS), (
        "the detector below cannot pass by seeing nothing — it must recognise "
        "the escape both enforcers actually carried"
    )


def test_c014_unit_003_neither_enforcer_carries_its_own_escape():
    """The ``total == 0`` free pass exists in the shared checker's policy or nowhere."""
    offenders = []
    for path in (_RUNTIME_GATE, _VALIDATOR):
        for hit in _escape_branches(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.name}:{hit}")

    assert not offenders, (
        "a second copy of the artifact-count escape reappeared — an empty "
        "declaration is a violation, and the policy lives in "
        "atdd/coach/utils/artifact_claims.py and nowhere else:\n  "
        + "\n  ".join(offenders)
    )


def test_c014_unit_003_the_runtime_gate_delegates_to_the_shared_checker():
    source = _RUNTIME_GATE.read_text(encoding="utf-8")
    assert "artifact_claims" in source, (
        "IssueManager must answer the artifacts question from the shared checker"
    )


def test_c014_unit_003_the_shared_checker_exists_exactly_once():
    """No sibling module re-implements the policy the checker owns."""
    assert _SHARED_CHECKER.is_file(), f"{_SHARED_CHECKER} does not exist"

    duplicates = []
    for path in sorted(_PKG.rglob("*.py")):
        if path == _SHARED_CHECKER or "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if "def check_artifact_claims" in source:
            duplicates.append(str(path.relative_to(_PKG)))

    assert not duplicates, f"the policy is implemented more than once: {duplicates}"
