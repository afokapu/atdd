# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C013-UNIT-004-the-vocabulary-is-total-and-the-module-stays-pure
# Acceptance: acc:govern-lifecycle:C013-UNIT-004-the-vocabulary-is-total-and-the-module-stays-pure
# WMBT: wmbt:govern-lifecycle:C013
# Phase: GREEN
# Layer: unit
# Assertion: structural
"""C013-UNIT-004 — the vocabulary is closed, and the module it lands in stays pure.

Two guarantees that would each be too small to stand alone, and that fail
together if the verdict is added carelessly.

**The vocabulary is total.** Every declared verdict must answer the blocking
question, and the answer is read off the enum rather than restated here — so a
fifth verdict added later is covered by construction instead of silently
defaulting to "proceed", which is the failure shape this whole WMBT is about.

``NOT_APPLICABLE`` is the member that carries the risk. It proceeds, which makes
it the one place a careless reader could re-collapse the distinction: it is *not*
``PASS``, because nothing was verified — the check established that it was owed
nothing. Keeping it separate is what lets ``SmokeExecutionGateCheck`` stop
spelling "there was no obligation" as "the obligation was met" without changing
any issue's lifecycle.

**The module stays pure.** ``decision.py`` is the #1020 keystone and its purity
contract (#955/#865) is stated in its docstring. The docstring was, at the time
this test was written, the only thing holding it: nothing in the tree asserted
the import list. A docstring is not a gate, so this is that gate.

RED state: ``atdd.coach.gate.decision`` declares no ``GateVerdict``.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from atdd.coach.gate import decision as decision_module
from atdd.coach.gate.decision import GateCheckResult, GateVerdict, evaluate_gate

pytestmark = [pytest.mark.platform]

_RULE = "repo.govern-lifecycle.c013"

#: Top-level modules ``decision.py`` may never reach for. Subprocess and the
#: network are the two the purity contract names; ``atdd.runtime`` and
#: ``atdd.integrations`` are the layering half of it.
_FORBIDDEN_ROOTS = frozenset(
    {"subprocess", "socket", "http", "urllib", "requests", "httpx", "git", "gh", "os"}
)
_FORBIDDEN_PREFIXES = ("atdd.runtime", "atdd.integrations")


def _imported_modules() -> set[str]:
    """Every module name ``decision.py`` imports, at any nesting depth."""
    source_file = inspect.getsourcefile(decision_module)
    assert source_file, "decision.py must be resolvable on disk to audit its imports"
    tree = ast.parse(open(source_file, encoding="utf-8").read())

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


# --------------------------------------------------------------------------- #
# The vocabulary is total                                                     #
# --------------------------------------------------------------------------- #
def test_every_declared_verdict_answers_the_blocking_question():
    """Read off the enum, so a verdict added later cannot default to silence."""
    assert len(list(GateVerdict)) >= 4, "the vocabulary must declare at least the four states"

    for verdict in GateVerdict:
        assert isinstance(verdict.blocks, bool), (
            f"{verdict} does not answer whether it blocks; an unanswered verdict "
            f"is exactly the ambiguity this WMBT removes"
        )


def test_not_applicable_proceeds_so_the_migration_changes_no_outcome():
    """The guarantee that keeps this a vocabulary correction, not a policy change."""
    assert GateVerdict.NOT_APPLICABLE.blocks is False

    outcome = evaluate_gate(
        [GateCheckResult.not_applicable("GT-NA", _RULE, "this issue owes the check nothing")]
    )

    assert outcome.proceed is True
    assert outcome.failures == ()
    assert outcome.unobservable == ()
    assert outcome.blockers == ()


def test_not_applicable_is_not_a_pass():
    """'There was nothing to observe' must not read as 'the observation succeeded'."""
    not_applicable = GateCheckResult.not_applicable("GT-NA", _RULE, "no obligation declared")
    a_pass = GateCheckResult.passing("GT-OK", _RULE, "observed and satisfied")

    assert not_applicable.verdict is not a_pass.verdict
    assert not_applicable.verdict is GateVerdict.NOT_APPLICABLE

    outcome = evaluate_gate([not_applicable, a_pass])

    assert [r.gate_id for r in outcome.passed_checks] == ["GT-OK"], (
        "a not-applicable result was reported as a verified pass; the two facts "
        "must stay distinguishable to the reader"
    )
    assert [r.gate_id for r in outcome.not_applicable] == ["GT-NA"]


def test_a_verdict_that_contradicts_its_legacy_bool_is_refused():
    """The two representations must not be able to drift apart unnoticed.

    ``passed`` is retained for callers that still read it, so for as long as both
    exist a construction that sets them against each other has to be an error
    rather than a silent reconciliation — silently picking a winner is how one
    fact becomes two.
    """
    with pytest.raises(ValueError):
        GateCheckResult(
            gate_id="GT-X",
            rule_id=_RULE,
            passed=True,
            message="claims to pass while carrying a blocking verdict",
            verdict=GateVerdict.COULD_NOT_CHECK,
        )

    with pytest.raises(ValueError):
        GateCheckResult(
            gate_id="GT-X",
            rule_id=_RULE,
            passed=False,
            message="claims to block while carrying a proceeding verdict",
            verdict=GateVerdict.NOT_APPLICABLE,
        )


def test_a_bare_bool_still_constructs_the_verdict_it_always_meant():
    """Every pre-existing call site keeps working, and lands on PASS/FAIL."""
    assert GateCheckResult("GT-A", _RULE, True, "ok").verdict is GateVerdict.PASS
    assert GateCheckResult("GT-B", _RULE, False, "bad").verdict is GateVerdict.FAIL


# --------------------------------------------------------------------------- #
# The module stays pure                                                       #
# --------------------------------------------------------------------------- #
def test_decision_module_imports_nothing_impure():
    """#955/#865/#1020's compliance bar, asserted rather than merely documented."""
    imported = _imported_modules()

    impure_roots = {name for name in imported if name.split(".")[0] in _FORBIDDEN_ROOTS}
    assert impure_roots == set(), (
        f"decision.py imports {sorted(impure_roots)}; the purity contract forbids "
        f"subprocess, networking and OS access in the gate's verdict logic"
    )

    layering_breaks = {
        name for name in imported if name.startswith(_FORBIDDEN_PREFIXES)
    }
    assert layering_breaks == set(), (
        f"decision.py imports {sorted(layering_breaks)}; the pure decision module "
        f"may not depend on atdd.runtime or atdd.integrations"
    )
