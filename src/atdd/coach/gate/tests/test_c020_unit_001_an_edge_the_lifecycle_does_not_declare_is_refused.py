# URN: test:govern-lifecycle:operator-approval-token-gate:C020-UNIT-001-an-edge-the-lifecycle-does-not-declare-is-refused
# Acceptance: acc:govern-lifecycle:C020-UNIT-001-an-edge-the-lifecycle-does-not-declare-is-refused
# WMBT: wmbt:govern-lifecycle:C020
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C020-UNIT-001 — the transition string is checked against the declared machine.

``_parse_transition`` split on ``->``, upper-cased both halves and returned them.
Nothing downstream questioned the result, so::

    atdd coach approve 1726 --transition 'BANANA->MOON'

produced a correctly signed token for an edge that does not exist — and, less
absurdly and more likely, ``INIT->RED`` produced one for a pair of REAL phases with
no edge between them. Both are properties of the string alone, so both are settled
here without reading any issue state.

TWO DISTINCT CHECKS, and the second is the one that matters in practice. Vocabulary
("is this a phase?") catches the typo. Legality ("is this an edge?") catches the
plausible mistake — every phase name spelled correctly, and a hop the lifecycle
never declared. An operator makes the second kind far more often than the first.

WHERE THE VOCABULARY COMES FROM. ``phase_machine.convention.yaml``, which says in
its own header: *add or change a phase HERE, never in Python and never in
CLAUDE.md.* This file asserts that discipline directly — the last test proves an
unreadable machine RAISES rather than falling back to a phase list written in
Python, because a hardcoded fallback would fork the single source of truth at
exactly the moment it cannot be consulted, and would fail OPEN.

RED state: ``_parse_transition`` returns ``("BANANA", "MOON")`` without complaint.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.approve_command import _parse_transition
from atdd.coach.gate.phase_edges import (
    PHASE_MACHINE_PATH,
    PhaseMachineUnavailable,
    phase_machine,
)

pytestmark = [pytest.mark.platform]


def test_a_real_declared_edge_still_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard discriminates rather than refusing everything.

    Read off the convention rather than hardcoded, so this cannot pass by agreeing
    with a stale copy of the machine.
    """
    machine = phase_machine()
    from_phase = "PLANNED"
    to_phase = machine[from_phase][0]

    assert _parse_transition(f"{from_phase}->{to_phase}") == (from_phase, to_phase)


def test_a_name_that_is_not_a_phase_is_refused() -> None:
    """The literal command from #1735's body, which mints happily today."""
    with pytest.raises(ValueError) as exc:
        _parse_transition("BANANA->MOON")

    message = str(exc.value)
    assert "BANANA" in message, message
    # The refusal must be actionable: name what IS declared, not merely what is not.
    assert "PLANNED" in message and "REFACTOR" in message, (
        f"the refusal does not enumerate the phases that do exist: {message!r}"
    )


def test_two_real_phases_with_no_edge_between_them_are_refused() -> None:
    """The plausible mistake: every name spelled right, the hop never declared.

    ``INIT`` goes to ``PLANNED``; there is no ``INIT->RED``. A parser that only
    checked vocabulary would accept this, which is why the two checks are separate.
    """
    machine = phase_machine()
    assert "RED" not in machine["INIT"], (
        "this test's premise moved: INIT now declares an edge to RED"
    )

    with pytest.raises(ValueError) as exc:
        _parse_transition("INIT->RED")

    message = str(exc.value)
    assert "INIT" in message and "RED" in message, message
    # Name the way out, not just the wall.
    assert "PLANNED" in message, (
        f"the refusal does not say which edges ARE reachable from INIT: {message!r}"
    )


def test_a_terminal_phase_offers_no_edges_and_says_so() -> None:
    """COMPLETE declares ``transitions_to: []``. The message must not be empty."""
    assert phase_machine()["COMPLETE"] == ()

    with pytest.raises(ValueError) as exc:
        _parse_transition("COMPLETE->RED")

    assert "terminal" in str(exc.value), str(exc.value)


def test_an_unreadable_machine_raises_instead_of_falling_back(tmp_path: Path) -> None:
    """No hardcoded phase list. Fail closed, not fail open.

    The tempting alternative is a Python fallback ``[INIT, PLANNED, RED, ...]``, as
    ``_acceptance_walker`` keeps for phase ORDER. It is wrong here for two reasons:
    the convention forbids a second copy of the vocabulary, and this copy would be
    consulted only when the real one is unreadable — the one moment it is most
    likely to disagree with it. The mint turns this into a refusal.
    """
    missing = tmp_path / "no-such-machine.yaml"

    with pytest.raises(PhaseMachineUnavailable):
        phase_machine(missing)

    unparseable = tmp_path / "broken.yaml"
    unparseable.write_text("phases: [this is a list, not a mapping]\n")
    with pytest.raises(PhaseMachineUnavailable):
        phase_machine(unparseable)


def test_the_machine_is_read_from_inside_the_package(tmp_path: Path) -> None:
    """It ships with the wheel, so a consumer repo reads the same declaration.

    Resolving it against a repo root would make the check work in this worktree and
    silently stop working for anyone running an installed atdd — which is the
    consumer-oracle failure #1474 exists to catch.
    """
    import atdd

    assert PHASE_MACHINE_PATH.is_file()
    assert PHASE_MACHINE_PATH.is_relative_to(Path(atdd.__file__).resolve().parent), (
        f"{PHASE_MACHINE_PATH} is outside the installed package"
    )
