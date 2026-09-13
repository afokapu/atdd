# URN: test:drive-state-machine:coach-state-machine-and-runtime:D004-UNIT-001-the-package-defines-one-phase-vocabulary
# Acceptance: acc:drive-state-machine:D004-UNIT-001-the-package-defines-one-phase-vocabulary
# Acceptance: acc:drive-state-machine:D004-UNIT-002-merged-is-not-a-phase
# Acceptance: acc:drive-state-machine:D004-UNIT-003-transition-tables-are-projections-of-the-convention
# Acceptance: acc:drive-state-machine:D004-UNIT-004-the-successor-function-has-one-definition
# Acceptance: acc:drive-state-machine:D004-UNIT-005-a-drifting-vocabulary-fails-a-test
# WMBT: wmbt:drive-state-machine:D004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""D004 — one phase vocabulary, projected from the convention (#1946).

``phase_machine.convention.yaml`` says in its own header: *add or change a phase
HERE, never in Python*. ``atdd.coach.gate.phase_edges`` honours that. Two Phase
enums nevertheless live inside ``atdd.coach`` and each raises on the other's
ninth member::

    handlers.state_machine.Phase : … BLOCKED MERGED
    coach.core.types.Phase       : … BLOCKED OBSOLETE

Both are ``str`` mixins, so ``handlers.Phase.COMPLETE == core.types.Phase.COMPLETE``
is ``True`` and membership in a ``frozenset`` of the other class succeeds. Only
``is`` separates them. That is why the fork survived from #496 unnoticed: nothing
fails until someone names the member the other side lacks.

MERGED is the member that should not exist at all. Every successor map stops at
COMPLETE, ``resume.py`` refuses to walk into it, and no production path assigns
it — the live notion of *merged* is ``PullRequest.state``. So this is not two
rival names for one phase; it is dead code that a projection deletes.

The oracle throughout is the convention, read through ``phase_edges.phase_machine()``
— the module that already reads the YAML and already fails closed. Asserting
against a hand-written phase list here would be the same second source of truth
the convention forbids.
"""
from __future__ import annotations

import itertools
from typing import Dict, Tuple

import pytest

from atdd.coach.gate.phase_edges import phase_machine

pytestmark = [pytest.mark.coach]

#: Off-spine phases: reachable from any rung, ordered against none. The same set
#: ``state/tests/test_phase_ladder_matches_projection_phases.py`` encodes.
#: The one definition (atdd.state.evidence). It had four copies before #1967,
#: and that issue ADDS a member to the set — restating it here is how the
#: phase vocabulary forked in #1946.
from atdd.state.evidence import ESCAPES  # noqa: F401


@pytest.fixture(scope="module")
def declared() -> Dict[str, Tuple[str, ...]]:
    """``{PHASE: (targets, …)}`` exactly as the convention declares it."""
    return phase_machine()


@pytest.fixture(scope="module")
def spine(declared) -> list[str]:
    """The linear chain: INIT, then each phase's one non-escape target.

    The same walk the #1602 drift guard performs. It is the oracle for
    ``PLANNED_PATH`` and for every per-phase successor map.
    """
    chain = ["INIT"]
    seen = {"INIT"}
    while True:
        forward = [t for t in declared[chain[-1]] if t not in ESCAPES]
        if not forward:
            return chain
        assert len(forward) == 1, (
            f"{chain[-1]} forks to {forward}; the phase machine is no longer a "
            "linear spine and a successor function has no single meaning"
        )
        assert forward[0] not in seen, f"the phase machine cycles back to {forward[0]}"
        seen.add(forward[0])
        chain.append(forward[0])


# --------------------------------------------------------------------------
# UNIT-001 — the package defines one phase vocabulary
# --------------------------------------------------------------------------


def test_the_coach_package_exposes_exactly_one_phase_enum() -> None:
    """Same object, not two classes that merely compare equal by value.

    ``==`` cannot see this fork — both are ``str`` mixins — so identity is the
    only assertion that can.
    """
    from atdd.coach.core.types import Phase as core_phase
    from atdd.coach.handlers.state_machine import Phase as handlers_phase

    assert handlers_phase is core_phase, (
        "atdd.coach defines two Phase enums; handlers/state_machine.py carries "
        "MERGED and cannot name OBSOLETE, core/types.py the reverse. They compare "
        "equal by value, so only identity catches the fork"
    )


def test_the_phase_vocabulary_is_exactly_what_the_convention_declares(declared) -> None:
    """No member the convention does not declare; no declared phase missing."""
    from atdd.coach.handlers.state_machine import Phase

    assert {p.value for p in Phase} == set(declared), (
        "the runtime phase vocabulary has drifted from phase_machine.convention.yaml"
    )


def test_every_declared_phase_can_be_named_by_the_runtime(declared) -> None:
    """The promise the convention header makes, asserted directly.

    ``Phase('OBSOLETE')`` raises today, which is the live half of #1946: an
    OBSOLETE issue cannot even be named by the module every transition decision
    goes through.
    """
    from atdd.coach.handlers.state_machine import Phase

    unnameable = []
    for name in declared:
        try:
            Phase(name)
        except ValueError:
            unnameable.append(name)
    assert unnameable == [], (
        f"the convention declares {unnameable} but the coach runtime cannot name "
        "them — a phase added to the YAML is invisible to the runtime"
    )


# --------------------------------------------------------------------------
# UNIT-002 — MERGED is not a phase
# --------------------------------------------------------------------------


def test_merged_is_not_a_phase(declared) -> None:
    """It is unreachable, and the convention never declared it."""
    from atdd.coach.handlers.state_machine import Phase

    assert "MERGED" not in declared, "the convention must not gain a MERGED phase"
    assert "MERGED" not in {p.value for p in Phase}, (
        "MERGED is a vestigial J1 (#496) terminal: every successor map stops at "
        "COMPLETE, resume.py refuses to walk into it, and no production path "
        "assigns it. Merge-ness is PullRequest.state"
    )


def test_no_phase_keyed_table_names_merged() -> None:
    """Not in the transition table, not on the planned path."""
    from atdd.coach.handlers.state_machine import PLANNED_PATH, TRANSITION_TABLE

    named = {str(p) for p in TRANSITION_TABLE}
    for targets in TRANSITION_TABLE.values():
        named |= {str(t) for t in targets}
    named |= {str(p) for p in PLANNED_PATH}
    assert "MERGED" not in named, (
        "a phase-keyed table still names MERGED; the phase is gone but a table "
        "kept a copy"
    )


def test_the_pull_request_state_vocabulary_still_carries_merged() -> None:
    """The concept keeps its real home — this change removes a phase, not a feature.

    ``coach/core/__init__.py`` reads ``pr.state != "MERGED"`` to reconcile a
    COMPLETE issue against its PR; that path must be untouched.
    """
    import typing

    from atdd.coach.core.types import PrState

    state = typing.get_type_hints(PrState)["state"]
    assert "MERGED" in typing.get_args(state), (
        "PrState.state must still admit MERGED — it is where merge-ness lives"
    )


def test_the_derived_label_set_names_obsolete_and_not_merged() -> None:
    """The GitHub label taxonomy is already derived from the convention.

    ``coach/validators/test_required_label_set.py`` builds it as
    ``tuple(f"atdd:{phase}" for phase in sorted(phase_machine()))``, so the
    runtime enum contradicting it is the inversion #1946 names.
    """
    labels = {f"atdd:{phase}" for phase in phase_machine()}
    assert "atdd:OBSOLETE" in labels
    assert "atdd:MERGED" not in labels


# --------------------------------------------------------------------------
# UNIT-003 — the tables are projections of the convention
# --------------------------------------------------------------------------


def test_the_transition_table_is_the_declared_edges(declared) -> None:
    """Both directions: nothing declared is refused, nothing undeclared is legal."""
    from atdd.coach.handlers.state_machine import TRANSITION_TABLE

    runtime = {str(src): {str(dst) for dst in targets} for src, targets in TRANSITION_TABLE.items()}
    expected = {name: set(targets) for name, targets in declared.items()}
    assert runtime == expected, (
        "TRANSITION_TABLE is not a projection of transitions_to; a Python literal "
        "and the convention disagree about which edges exist"
    )


def test_the_planned_path_is_the_spine(spine) -> None:
    """``PLANNED_PATH`` is the convention's linear chain, escapes excluded."""
    from atdd.coach.handlers.state_machine import PLANNED_PATH

    assert [str(p) for p in PLANNED_PATH] == spine


def test_a_phase_added_to_the_convention_appears_without_a_source_edit(tmp_path) -> None:
    """The convention's central promise, exercised on a disposable copy.

    Read through ``phase_machine(path)`` — the loader the runtime uses — so this
    asserts the mechanism, not a re-implementation of it.
    """
    import yaml

    from atdd.coach.gate.phase_edges import PHASE_MACHINE_PATH

    data = yaml.safe_load(PHASE_MACHINE_PATH.read_text(encoding="utf-8"))
    data["phases"]["DISCOVERY"] = {
        "agent": None,
        "transitions_to": ["PLANNED", "BLOCKED", "OBSOLETE"],
        "autonomy": None,
    }
    data["phases"]["INIT"]["transitions_to"] = ["DISCOVERY", "BLOCKED", "OBSOLETE"]
    copy = tmp_path / "phase_machine.convention.yaml"
    copy.write_text(yaml.safe_dump(data), encoding="utf-8")

    extended = phase_machine(copy)
    assert "DISCOVERY" in extended
    assert extended["INIT"] == ("DISCOVERY", "BLOCKED", "OBSOLETE")


# --------------------------------------------------------------------------
# UNIT-004 — the successor function has one definition
# --------------------------------------------------------------------------


def _successor(spine: list[str]) -> Dict[str, str]:
    return dict(itertools.pairwise(spine))


@pytest.mark.parametrize(
    "module_path, table_name",
    [
        ("atdd.coach.commands.coach", "_COLD_START_ADVANCE_FROM"),
        ("atdd.coach.handlers.watcher", "_ADVANCE_FROM"),
        ("atdd.coach.commands.auto_phase", "_NEXT_PHASE"),
    ],
)
def test_every_successor_map_agrees_with_the_spine(spine, module_path, table_name) -> None:
    """Five copies of one fact; each must read it rather than restate it.

    Each map is keyed and valued either by Phase or by bare string — normalising
    through ``str`` compares them on the one thing that matters, the phase name.
    """
    import importlib

    module = importlib.import_module(module_path)
    table = getattr(module, table_name)
    successor = _successor(spine)

    actual = {str(src): str(dst) for src, dst in table.items()}
    disagreements = {
        src: (dst, successor.get(src))
        for src, dst in actual.items()
        if successor.get(src) != dst
    }
    assert disagreements == {}, (
        f"{module_path}.{table_name} disagrees with the convention's spine "
        f"(phase: (declared, spine)) — {disagreements}"
    )


# --------------------------------------------------------------------------
# UNIT-005 — a drifting vocabulary fails a test
# --------------------------------------------------------------------------


def test_the_core_phase_enum_is_pinned_to_the_convention(declared) -> None:
    """``core.types.Phase`` stays a literal by decision — so a test pins it.

    Deriving it would cost static typing across ``train/``, ``state/`` and every
    ``Phase.X`` reference (issue #1946 Decision 3). It fails loudly rather than
    silently, at ``load_conventions``. This is the assertion that would have
    caught the fork.
    """
    from atdd.coach.core.types import Phase

    assert {p.value for p in Phase} == set(declared), (
        "core.types.Phase has drifted from phase_machine.convention.yaml; it is "
        "what train/persistence.py coerces every YAML phase name through, so a "
        "drift here fails convention LOADING, before the coach runtime is reached"
    )


def test_the_projection_and_the_ladder_stay_tied_to_the_convention(declared, spine) -> None:
    """The two vocabularies the #1602 guard already pins, restated against D004's oracle.

    ``PHASES`` omits COMPLETE (derived from merge-to-main, spec §18 decision 1);
    ``PHASE_LADDER`` omits the escapes. Both are stated exclusions, not gaps.
    """
    from atdd.state.evidence import PHASE_LADDER
    from atdd.state.projection import ARCHIVED_PHASES, PHASES

    assert set(PHASES) | set(ARCHIVED_PHASES) == set(declared)
    assert list(PHASE_LADDER) == spine
    assert set(declared) - set(PHASE_LADDER) == ESCAPES


#: The successor maps deliberately omit the phases whose forward transition is an
#: operator sign-off (``autonomy: operator`` on INIT and PLANNED). A derivation test
#: must not assert they cover the whole spine — they cover the autonomous part of it.
_OPERATOR_GATED = {"INIT", "PLANNED"}


@pytest.mark.parametrize(
    "module_path, table_name",
    [
        ("atdd.coach.commands.coach", "_COLD_START_ADVANCE_FROM"),
        ("atdd.coach.handlers.watcher", "_ADVANCE_FROM"),
        ("atdd.coach.commands.auto_phase", "_NEXT_PHASE"),
    ],
)
def test_a_reordered_spine_is_followed(tmp_path, monkeypatch, module_path, table_name) -> None:
    """The assertion that forces derivation rather than coincidence.

    The maps AGREE with the spine today — they were written to, and the spine has
    not moved since. Agreement is not derivation: the comparison test above passes
    against five hardcoded literals. This one does not.

    SWAPPING two rungs rather than inserting a new one is deliberate. An inserted
    phase cannot be typed, because ``core.types.Phase`` stays a literal by decision
    (see the Done-when test below), so an insertion would measure that decision
    rather than the derivation. A swap uses only members the enum already has, and
    a hardcoded map cannot follow it.
    """
    import importlib

    import yaml

    from atdd.coach.gate import phase_edges

    data = yaml.safe_load(phase_edges.PHASE_MACHINE_PATH.read_text(encoding="utf-8"))
    # GREEN -> SMOKE -> REFACTOR  becomes  SMOKE -> GREEN -> REFACTOR
    data["phases"]["RED"]["transitions_to"] = ["SMOKE", "BLOCKED", "OBSOLETE"]
    data["phases"]["SMOKE"]["transitions_to"] = ["GREEN", "BLOCKED", "OBSOLETE"]
    data["phases"]["GREEN"]["transitions_to"] = ["REFACTOR", "BLOCKED", "OBSOLETE"]
    copy = tmp_path / "phase_machine.convention.yaml"
    copy.write_text(yaml.safe_dump(data), encoding="utf-8")

    module = importlib.import_module(module_path)
    monkeypatch.setattr(phase_edges, "PHASE_MACHINE_PATH", copy)
    try:
        reloaded = importlib.reload(module)
        table = {str(s): str(d) for s, d in getattr(reloaded, table_name).items()}
    finally:
        monkeypatch.undo()
        importlib.reload(module)

    assert table.get("RED") == "SMOKE" and table.get("SMOKE") == "GREEN", (
        f"{module_path}.{table_name} did not follow the reordered spine "
        f"(RED -> {table.get('RED')}, SMOKE -> {table.get('SMOKE')}); it restates "
        "the successor function rather than reading it"
    )


def test_the_maps_cover_the_autonomous_spine_and_no_more(spine) -> None:
    """They stop where operator sign-off begins, and that is a property of the
    convention's ``autonomy`` axis, not an arbitrary omission."""
    import importlib

    for module_path, table_name, gated in (
        ("atdd.coach.commands.coach", "_COLD_START_ADVANCE_FROM", {"INIT"}),
        ("atdd.coach.handlers.watcher", "_ADVANCE_FROM", _OPERATOR_GATED),
        ("atdd.coach.commands.auto_phase", "_NEXT_PHASE", _OPERATOR_GATED),
    ):
        table = {
            str(s): str(d)
            for s, d in getattr(importlib.import_module(module_path), table_name).items()
        }
        want = {s: d for s, d in itertools.pairwise(spine) if s not in gated}
        assert table == want, f"{module_path}.{table_name} != the autonomous spine"


def test_adding_a_phase_costs_exactly_one_python_edit(tmp_path, monkeypatch, declared) -> None:
    """The Done-when, stated at the precision the design actually delivers.

    #1946 collapsed ten hand-maintained phase tables into projections. ONE literal
    survives by decision: ``core.types.Phase`` (deriving it would cost static typing
    across ``train/``, ``state/`` and every ``Phase.X`` site). So a new phase is a
    YAML edit plus a single enum member — not "no Python edit", and not ten.

    This test measures that cost rather than asserting the aspiration: with the enum
    member absent the typed projections refuse, and the string-keyed one already
    carries the phase.
    """
    import importlib

    import yaml

    from atdd.coach.gate import phase_edges

    data = yaml.safe_load(phase_edges.PHASE_MACHINE_PATH.read_text(encoding="utf-8"))
    data["phases"]["DISCOVERY"] = {
        "agent": "planner", "transitions_to": ["PLANNED", "BLOCKED", "OBSOLETE"],
        "autonomy": "operator",
    }
    data["phases"]["INIT"]["transitions_to"] = ["DISCOVERY", "BLOCKED", "OBSOLETE"]
    copy = tmp_path / "phase_machine.convention.yaml"
    copy.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setattr(phase_edges, "PHASE_MACHINE_PATH", copy)

    # The convention layer needs no Python at all.
    assert "DISCOVERY" in phase_edges.phase_machine()
    assert phase_edges.spine()[:2] == ("INIT", "DISCOVERY")

    # The string-keyed projection carries it with no edit.
    try:
        auto = importlib.reload(importlib.import_module("atdd.coach.commands.auto_phase"))
        assert auto._NEXT_PHASE.get("DISCOVERY") == "PLANNED"

        # The typed projections refuse, nameably, until the enum gains the member —
        # the one edit, in one place, that D004-UNIT-005 pins to the convention.
        with pytest.raises(ValueError, match="DISCOVERY"):
            importlib.reload(importlib.import_module("atdd.coach.handlers.state_machine"))
    finally:
        monkeypatch.undo()
        for m in ("atdd.coach.handlers.state_machine", "atdd.coach.commands.auto_phase",
                  "atdd.coach.commands.coach", "atdd.coach.handlers.watcher"):
            importlib.reload(importlib.import_module(m))
