"""#1967 — RESOLVED sits beside the ladder, and ESCAPES is defined once.

Two guarantees that are easy to state and were expensive to discover.

FIRST: declaring ``RESOLVED`` as an ordinary target of ``INIT`` does not degrade
gracefully. ``_forward_target`` refuses a phase with two non-escape targets, so
``spine()`` raises ``PhaseMachineUnavailable`` — and since ``TRANSITION_TABLE``
and ``PLANNED_PATH`` are projected AT IMPORT (#1946), that raise means the coach
runtime does not load at all. The phase machine became more powerful and
correspondingly less forgiving: a malformed phase is now a hard boot failure
rather than a silent divergence. So ``RESOLVED`` must be an escape, and this
test is what says so before someone discovers it the other way.

SECOND: ``ESCAPES`` had THREE definitions when this issue was written —
``evidence.py``, ``phase_edges.py``, and a test fixture — and this change adds a
member to the set. Adding to a forked constant is exactly how the phase
vocabulary forked in the first place (#1946), one layer down. The set now lives
in ``atdd.state.evidence`` and ``phase_edges`` imports it, because coach may
import state and state may never import coach.
"""
from __future__ import annotations

import pytest

LADDER = ("INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE")


def test_escapes_has_one_definition():
    """phase_edges must not keep its own copy; it imports the state-owned set."""
    from atdd.coach.gate import phase_edges
    from atdd.state import evidence

    assert phase_edges.ESCAPES is evidence.ESCAPES, (
        "ESCAPES is forked. coach may import state; state may never import coach, "
        "so atdd.state.evidence owns the set and phase_edges imports it."
    )


def test_resolved_is_an_escape_in_the_one_definition():
    from atdd.state.evidence import ESCAPES

    assert {"BLOCKED", "OBSOLETE", "RESOLVED"} <= ESCAPES


def test_the_spine_is_still_the_delivery_ladder():
    """RESOLVED must not appear on the linear chain."""
    from atdd.coach.gate.phase_edges import spine

    assert spine() == LADDER


def test_init_still_has_exactly_one_successor():
    from atdd.coach.gate.phase_edges import successor

    assert successor()["INIT"] == "PLANNED"


def test_resolved_is_declared_terminal_by_the_convention():
    from atdd.coach.gate.phase_edges import declared_autonomy, phase_machine

    machine = phase_machine()
    assert "RESOLVED" in machine, "the convention must declare RESOLVED"
    assert machine["RESOLVED"] == (), "RESOLVED is terminal: no transitions out"
    assert declared_autonomy("RESOLVED") is None, (
        "autonomy governs the FORWARD edge and a terminal has none, so it declares "
        "null like COMPLETE and OBSOLETE. That entering RESOLVED is an operator "
        "decision is enforced by the evidence policy, not by this key."
    )


def test_init_declares_resolved_as_a_target():
    from atdd.coach.gate.phase_edges import phase_machine

    assert "RESOLVED" in phase_machine()["INIT"]


def test_the_runtime_projects_resolved_without_a_python_phase_list():
    """The #1946 guarantee still holds: a phase added in YAML reaches the runtime."""
    from atdd.coach.handlers.state_machine import Phase, TRANSITION_TABLE

    assert Phase("RESOLVED")
    assert TRANSITION_TABLE[Phase("RESOLVED")] == set()
    assert Phase("RESOLVED") in TRANSITION_TABLE[Phase("INIT")]


def test_a_non_escape_fork_is_refused_loudly(tmp_path):
    """The trap, pinned: a second non-escape target on INIT breaks the walk."""
    from atdd.coach.gate.phase_edges import (
        PhaseMachineUnavailable, spine,
    )

    forked = {
        "INIT": ("PLANNED", "SOMETHING_ELSE", "BLOCKED"),
        "PLANNED": (), "SOMETHING_ELSE": (),
    }
    with pytest.raises(PhaseMachineUnavailable, match="non-escape targets"):
        spine(forked)
