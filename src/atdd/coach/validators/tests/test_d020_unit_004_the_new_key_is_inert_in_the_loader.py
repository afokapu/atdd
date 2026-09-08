# URN: test:govern-lifecycle:define-transition-autonomy:D020-UNIT-004-the-new-key-is-inert-in-the-loader
# Acceptance: acc:govern-lifecycle:D020-UNIT-004-the-new-key-is-inert-in-the-loader
# WMBT: wmbt:govern-lifecycle:D020
# Phase: GREEN
# Layer: application
# Assertion: behavioral
"""D020-UNIT-004 — adding the axis changes nothing the runtime can observe.

This is the acceptance that makes "declare first, enforce later" safe rather
than merely sequenced. ``_phase_machine_from_data`` builds PhaseSpec by reading
NAMED keys, and ``_normalized_snapshot`` derives the conventions snapshot hash
from the built PhaseSpec objects — not from the YAML text. So a key PhaseSpec
does not read cannot move the hash, and no in-flight run resuming from a frozen
``conventions.snapshot.yaml`` is invalidated by this issue.

TRIPWIRE: projecting ``autonomy`` onto PhaseSpec — which a mechanical submitter
check will need — WILL move that hash. These assertions are what make that
visible rather than silent, so a later track cannot extend PhaseSpec without
noticing it invalidates every frozen run snapshot.
"""
from __future__ import annotations

import copy

import pytest

from atdd.coach.utils.repo import find_repo_root

from ._d020_autonomy import PRE_CHANGE_SNAPSHOT_HASH, machine_data as _machine_data

pytestmark = [pytest.mark.coach, pytest.mark.platform]


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
        "REGRESSION: no phase declares `autonomy`, so 'the key is inert' would "
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
        "REGRESSION: stripping `autonomy` changed nothing, because the axis is "
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
    assert conventions.snapshot_hash == PRE_CHANGE_SNAPSHOT_HASH, (
        "the conventions snapshot hash has moved from the pre-change baseline "
        f"{PRE_CHANGE_SNAPSHOT_HASH} to {conventions.snapshot_hash}. If this is "
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
