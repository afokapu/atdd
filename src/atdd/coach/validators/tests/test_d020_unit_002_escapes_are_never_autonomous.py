# URN: test:govern-lifecycle:define-transition-autonomy:D020-UNIT-002-escapes-are-never-autonomous
# Acceptance: acc:govern-lifecycle:D020-UNIT-002-escapes-are-never-autonomous
# WMBT: wmbt:govern-lifecycle:D020
# Phase: GREEN
# Layer: unit
# Assertion: structural
"""D020-UNIT-002 — BLOCKED and OBSOLETE are never entered autonomously.

The per-phase ``autonomy`` scalar governs a phase's FORWARD transition only.
That leaves the escape edges — every phase's transition into BLOCKED or
OBSOLETE — governed by nothing in the data, which is why the invariant has to
be carried explicitly by the node's prose and asserted here. Without this the
escapes would be the one part of the machine the axis silently does not cover.

The escape set is NAMED, not derived — see ``_ESCAPES``. D020-UNIT-002 asks for
a derivation, but none is sound: BLOCKED does not appear in its own
``transitions_to``, so any "reachable from every rung" rule silently drops it.
``test_escape_set_agrees_with_the_ladder_walk`` is the achievable version, tying
this constant to the one the State Store's ladder test already walks by.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

from ._d020_autonomy import NODE_REL, node_prose, phases as _phases

pytestmark = [pytest.mark.coach, pytest.mark.platform]


#: The escape set, NAMED rather than derived — the same constant, for the same
#: reason, as src/atdd/state/tests/test_phase_ladder_matches_projection_phases.py.
#: BLOCKED cannot be derived from the topology: an escape is reachable from every
#: spine rung, but BLOCKED does not appear in its OWN transitions_to, so any
#: "reachable from all" derivation silently drops it. The machine names its
#: escapes; so does this test. See the RED report on #1626 — the acceptance's
#: "expressed against the escape SET" clause is not well-founded as a derivation,
#: and `test_escape_set_agrees_with_the_ladder_walk` is the achievable version:
#: it ties this constant to the repo's existing one so the two cannot drift apart.
_ESCAPES = {"BLOCKED", "OBSOLETE"}


def _spine(phases: dict) -> list:
    """The convention's linear chain: INIT, then each phase's one non-escape target."""
    chain = ["INIT"]
    seen = {"INIT"}
    while True:
        forward = [
            target
            for target in (phases.get(chain[-1]) or {}).get("transitions_to") or []
            if target not in _ESCAPES
        ]
        if not forward:
            return chain
        assert len(forward) == 1, f"{chain[-1]} forks to {forward}; the machine is not a linear spine"
        assert forward[0] not in seen, f"the phase machine cycles back to {forward[0]}"
        seen.add(forward[0])
        chain.append(forward[0])


def _derive_escape_targets(phases: dict) -> set:
    """The escape targets actually present in the machine, cross-checked against _ESCAPES."""
    reachable = {
        target
        for spec in phases.values()
        for target in (spec or {}).get("transitions_to") or []
    }
    return _ESCAPES & reachable


@pytest.mark.platform
def test_the_escape_set_is_blocked_and_obsolete() -> None:
    """Both named escapes are real targets in the machine, not stale constants."""
    escapes = _derive_escape_targets(_phases())
    assert escapes == _ESCAPES, (
        "the named escape set is not fully present in the machine's transitions; "
        f"expected {sorted(_ESCAPES)}, found reachable {sorted(escapes)}"
    )


@pytest.mark.platform
def test_escape_set_agrees_with_the_ladder_walk() -> None:
    """This file's escape constant cannot drift from the repo's existing one.

    The achievable version of the acceptance's "expressed against the escape SET"
    clause: rather than deriving escapes (which cannot be done soundly — see
    _ESCAPES), tie this constant to the one the State Store's ladder test already
    walks by. If a tenth escape is added, both must be updated together or the
    spine walk here forks and this fails.
    """
    from atdd.state.tests.test_phase_ladder_matches_projection_phases import ESCAPES

    assert _ESCAPES == ESCAPES, (
        "this file's escape set has drifted from the ladder walk's ESCAPES "
        f"({sorted(_ESCAPES)} vs {sorted(ESCAPES)}); a phase that is an escape in "
        "one and not the other falls outside exactly one of the two checks"
    )
    phases = _phases()
    spine = _spine(phases)
    assert spine[0] == "INIT" and spine[-1] == "COMPLETE", (
        f"the spine walk no longer runs INIT -> COMPLETE; got {spine}"
    )
    assert not (set(spine) & _ESCAPES), "an escape appears on the forward spine"


@pytest.mark.platform
def test_the_node_states_the_escape_invariant() -> None:
    """The invariant lives in prose a reader can find, not only in a scalar's definition."""
    node_path = find_repo_root() / NODE_REL
    assert node_path.is_file(), (
        f"REGRESSION: {NODE_REL} does not exist yet. GREEN authors the "
        "convention node that states the escape invariant."
    )
    prose = node_prose(yaml.safe_load(node_path.read_text(encoding="utf-8")) or {})
    for escape in sorted(_derive_escape_targets(_phases())):
        assert escape in prose, (
            f"the node's prose never names {escape}, so the escape invariant is "
            "left to be inferred from the scalar's definition rather than stated"
        )


@pytest.mark.platform
def test_leaving_blocked_is_operator_submitted() -> None:
    """An escape is symmetric: operator decision to enter, operator decision to leave."""
    phases = _phases()
    blocked = phases.get("BLOCKED") or {}
    assert "autonomy" in blocked, (
        "REGRESSION: BLOCKED declares no `autonomy` key, so nothing says who "
        "may submit a transition out of it"
    )
    assert blocked["autonomy"] == "operator", (
        "BLOCKED must declare `autonomy: operator` — an escape entered by "
        f"operator decision is left by one too; got {blocked['autonomy']!r}"
    )


@pytest.mark.platform
def test_no_escape_target_is_reachable_autonomously() -> None:
    """No phase's declaration permits autonomous entry into an escape.

    The scalar governs the forward edge only, so this holds structurally: an
    escape target must never appear as a phase's forward successor. If a future
    edit made an escape the sole successor of an `autonomy: agent` phase, the
    scalar WOULD authorise entering it autonomously. That is the hole this
    closes.
    """
    phases = _phases()
    escapes = _derive_escape_targets(phases)
    offenders = []
    for name, spec in phases.items():
        spec = spec or {}
        if spec.get("autonomy") != "agent":
            continue
        forward = [t for t in (spec.get("transitions_to") or []) if t not in escapes]
        if not forward:
            offenders.append(name)
    assert not offenders, (
        "these phases declare `autonomy: agent` but have no non-escape successor, "
        f"so their scalar would authorise entering an escape autonomously: {offenders}"
    )
