# URN: test:govern-lifecycle:operator-approval-token-gate:C021-UNIT-003-zero-substantive-checks-is-could-not-check-and-the-approval-check-is-excluded
# Acceptance: acc:govern-lifecycle:C021-UNIT-003-zero-substantive-checks-is-could-not-check-and-the-approval-check-is-excluded
# WMBT: wmbt:govern-lifecycle:C021
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C021-UNIT-003 — evaluating zero checks is not a clean gate, and the approval
check is excluded from its own precondition.

TWO RULES, ONE MECHANISM.

The first is #1632's, applied to the gate's own coverage: *a run that evaluated
0 of N must not be readable as one that evaluated N and found nothing.* #1619
makes this concrete rather than theoretical — ``register_approval_checks()`` has
exactly one non-test caller, ``issue_transition.py:155``, so every process that
is not ``atdd coach transition`` sees an EMPTY ``GATE_REGISTRY``. The mint is one
of those processes. An empty registry must therefore be ``COULD_NOT_CHECK``.

It cannot inherit that answer from ``evaluate_transition_gate``, which *proceeds*
on an empty registry — deliberately, as WMBT D019's migration-safety guarantee.
That is the right answer to "may this transition happen"; it is the wrong answer
to "may I sign an assertion that it was checked". So the mint composes
``run_checks`` and ``evaluate_gate`` itself.

The second is what makes the count honest. ``ApprovalTokenGateCheck`` is
registered on this edge, and a mint that consulted it would decide whether to
write an approval by asking whether an approval already exists — signing a
receipt for its own existence, the defect this program is named for. Excluding it
is also exactly why slice C is scoped to ``SMOKE->REFACTOR``: on the four other
forward edges the exclusion leaves nothing at all, and this file proves that a
registry holding only the approval check refuses rather than passes.

RED state: ``atdd.coach.gate.mint_gate`` does not exist.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.gate.approval_check import GATE_ID as APPROVAL_GATE_ID
from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.decision import GateVerdict
from atdd.coach.gate.mint_gate import DEFAULT_REGISTRARS, decide_mint
from atdd.coach.gate.registry import GateRegistry
from atdd.coach.gate.smoke_execution_check import GATE_ID as SMOKE_GATE_ID

pytestmark = [pytest.mark.platform]

_ISSUE = 999023


def _worktree(tmp_path: Path) -> Path:
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "gate:\n  transitions:\n    SMOKE->REFACTOR: true\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit",
         "-q", "--allow-empty", "-m", "root"],
        cwd=tmp_path, check=True,
    )
    return tmp_path


def _decide(worktree: Path, registry: GateRegistry):
    return decide_mint(
        worktree, _ISSUE, "SMOKE", "REFACTOR", registry=registry, registrars=()
    )


def test_an_empty_registry_refuses_the_mint(tmp_path):
    """The #1619 state every non-transition process is in today."""
    decision = _decide(_worktree(tmp_path), GateRegistry())

    assert decision.proceed is False, (
        "an empty registry authorised the mint — zero checks evaluated was read "
        "as a gate that ran and found nothing wrong (#1632's rule, #1619's state)"
    )
    assert decision.verdict is GateVerdict.COULD_NOT_CHECK, (
        "an unpopulated registry is an unmade observation, not an observed "
        "violation; the operator's remedy is to populate it, not to fix code"
    )


def test_a_registry_holding_only_the_approval_check_refuses(tmp_path):
    """The shape of the four bare forward edges — and the reason for the scope.

    If this passed, slice C could be widened to all five edges. It must not: the
    mint would be consulting the check whose artifact it is producing.
    """
    registry = GateRegistry()
    registry.register("SMOKE", "REFACTOR", ApprovalTokenGateCheck())
    decision = _decide(_worktree(tmp_path), registry)

    assert decision.proceed is False
    assert decision.verdict is GateVerdict.COULD_NOT_CHECK
    assert decision.coverage.evaluated == 0
    assert decision.coverage.excluded == 1


def test_the_approval_check_is_never_run_by_the_mint(tmp_path):
    """Not merely uncounted — never invoked.

    Excluding it from the tally while still running it would leave the mint's
    verdict depending on whether the token it is about to write already exists.
    """
    ran = []

    class _Spy(ApprovalTokenGateCheck):
        def run(self, ctx):  # noqa: D102 - the assertion is that this never fires
            ran.append(ctx)
            raise AssertionError(
                "the mint invoked ApprovalTokenGateCheck — it is deciding whether "
                "to write an approval by asking whether an approval exists"
            )

    registry = GateRegistry()
    registry.register("SMOKE", "REFACTOR", _Spy())
    _decide(_worktree(tmp_path), registry)

    assert ran == []


def test_the_report_names_the_count_and_the_exclusion(tmp_path):
    """A refusal an operator cannot act on is barely better than a vacuous pass."""
    registry = GateRegistry()
    registry.register("SMOKE", "REFACTOR", ApprovalTokenGateCheck())
    rendered = _decide(_worktree(tmp_path), registry).render()

    assert APPROVAL_GATE_ID in rendered, (
        "the report must name the check it excluded, or the operator cannot tell "
        "an unpopulated registry from a gate that genuinely evaluated nothing"
    )
    assert "0" in rendered


def test_the_mint_registers_the_same_checks_the_transition_dispatch_registers(tmp_path):
    """A mint against a different registry certifies the wrong gate set.

    ``issue_transition.run()`` calls both registrars before applying a
    transition. The mint must call the same two, or it certifies a set that is
    not the one ``atdd coach transition`` will run.
    """
    from atdd.coach.commands import issue_transition
    from atdd.coach.gate import registrations

    source = Path(issue_transition.__file__).read_text()
    for registrar in DEFAULT_REGISTRARS:
        assert registrar.__name__ in source, (
            f"the mint registers {registrar.__name__} but the transition dispatch "
            f"does not, so the mint would certify a check the gate never runs"
        )
        assert getattr(registrations, registrar.__name__) is registrar

    # And they do populate this edge, so the guard above is not vacuous.
    registry = GateRegistry()
    for registrar in DEFAULT_REGISTRARS:
        registrar(registry)
    gate_ids = {getattr(c, "gate_id", None) for c in registry.checks_for("SMOKE", "REFACTOR")}
    assert {APPROVAL_GATE_ID, SMOKE_GATE_ID} <= gate_ids


def test_a_populated_registry_with_a_substantive_check_is_evaluated(tmp_path):
    """The discriminating control: the refusal is the empty set, not the branch."""
    registry = GateRegistry()
    for registrar in DEFAULT_REGISTRARS:
        registrar(registry)
    decision = _decide(_worktree(tmp_path), registry)

    assert decision.coverage.evaluated == 1, (
        "the real registrars populate this edge with one substantive check and "
        "the approval check; exactly one should have been evaluated"
    )
    assert decision.coverage.excluded == 1
