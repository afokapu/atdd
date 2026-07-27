# URN: test:govern-lifecycle:define-transition-autonomy:D020-UNIT-004-the-new-key-is-inert-in-the-loader
# Acceptance: acc:govern-lifecycle:D020-UNIT-004-the-new-key-is-inert-in-the-loader
# WMBT: wmbt:govern-lifecycle:D020
# Phase: RED
# Layer: application
# Assertion: behavioral
"""D020-UNIT-004 — adding the axis changes nothing the runtime can observe.

Phase: RED. The axis does not exist, so the "the machine declares it" clause
below fails; the inertness clauses are what GREEN must keep true.

This is the acceptance that makes "declare first, enforce later" safe rather
than merely sequenced. ``_phase_machine_from_data`` builds PhaseSpec by reading
NAMED keys, and ``_normalized_snapshot`` derives the conventions snapshot hash
from the built PhaseSpec objects — not from the YAML text. So a key PhaseSpec
does not read cannot move the hash, and no in-flight run resuming from a frozen
``conventions.snapshot.yaml`` is invalidated by this issue.

NOTE for GREEN: projecting ``autonomy`` onto PhaseSpec — which a mechanical
submitter check will need — WILL move that hash. This test is the tripwire that
makes that visible rather than silent.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.platform]

_MACHINE_REL = Path("src/atdd/coach/conventions/phase_machine.convention.yaml")

#: The conventions snapshot hash measured on 2026-07-26, BEFORE the autonomy
#: axis was authored, via load_conventions(repo_root).snapshot_hash. GREEN must
#: not move it.
_PRE_CHANGE_SNAPSHOT_HASH = (
    "88af3062dfd486ee0d206946e82bebe408a3718873673f11bc0960f14e4e0913"
)


def _machine_data() -> dict:
    return yaml.safe_load(
        (find_repo_root() / _MACHINE_REL).read_text(encoding="utf-8")
    ) or {}


def _without_autonomy(data: dict) -> dict:
    stripped = copy.deepcopy(data)
    for spec in (stripped.get("phases") or {}).values():
        if isinstance(spec, dict):
            spec.pop("autonomy", None)
    return stripped


@pytest.mark.platform
def test_the_machine_declares_the_axis() -> None:
    """Precondition: without the axis the inertness claim is vacuously true."""
    phases = _machine_data().get("phases") or {}
    declaring = [name for name, spec in phases.items() if "autonomy" in (spec or {})]
    assert declaring, (
        "Phase: RED — no phase declares `autonomy`, so 'the key is inert' would "
        "pass trivially and prove nothing. GREEN adds the axis; this assertion "
        "is what keeps the rest of this file honest."
    )


@pytest.mark.platform
def test_phase_spec_is_identical_with_and_without_the_axis() -> None:
    """The new key reaches no PhaseSpec field."""
    from atdd.train.persistence import _phase_machine_from_data

    data = _machine_data()
    with_axis = _phase_machine_from_data(data)
    without_axis = _phase_machine_from_data(_without_axis_guard(data))

    assert with_axis == without_axis, (
        "PhaseSpec differs with and without the autonomy key, so the key is no "
        "longer inert — the loader now reads it. That is a real change to run "
        "semantics and must be taken deliberately, not as a side effect."
    )


def _without_axis_guard(data: dict) -> dict:
    """Strip the axis, asserting it was actually present so the diff is meaningful."""
    stripped = _without_autonomy(data)
    assert stripped != data, (
        "Phase: RED — stripping `autonomy` changed nothing, because the axis is "
        "not declared yet; the with/without comparison has no subject."
    )
    return stripped


@pytest.mark.platform
def test_snapshot_hash_is_identical_with_and_without_the_axis() -> None:
    """The conventions snapshot hash is derived from PhaseSpec, so it cannot move."""
    from atdd.train.persistence import _normalized_snapshot, _phase_machine_from_data

    data = _machine_data()
    with_axis = _normalized_snapshot(_phase_machine_from_data(data))
    without_axis = _normalized_snapshot(_phase_machine_from_data(_without_axis_guard(data)))

    assert with_axis == without_axis, (
        "the normalized conventions snapshot differs with and without the "
        "autonomy key — an in-flight run's frozen snapshot would no longer match"
    )


@pytest.mark.platform
def test_live_snapshot_hash_equals_the_pre_change_baseline() -> None:
    """The shipped machine still hashes to what it hashed before the axis existed."""
    from atdd.train.persistence import load_conventions

    conventions = load_conventions(find_repo_root())
    assert conventions.snapshot_hash == _PRE_CHANGE_SNAPSHOT_HASH, (
        "the conventions snapshot hash has moved from the pre-change baseline "
        f"{_PRE_CHANGE_SNAPSHOT_HASH} to {conventions.snapshot_hash}. If this is "
        "because PhaseSpec now carries `autonomy`, that is the follow-up track's "
        "change and is out of scope for #1626 — see the module docstring."
    )


@pytest.mark.platform
def test_all_nine_phases_still_load() -> None:
    """The new key breaks no parse and drops no phase."""
    from atdd.train.persistence import load_conventions

    loaded = {phase.value for phase in load_conventions(find_repo_root()).phase_machine}
    expected = {
        "INIT", "PLANNED", "RED", "GREEN", "SMOKE",
        "REFACTOR", "COMPLETE", "BLOCKED", "OBSOLETE",
    }
    assert loaded == expected, f"expected the nine phases, loaded {sorted(loaded)}"
