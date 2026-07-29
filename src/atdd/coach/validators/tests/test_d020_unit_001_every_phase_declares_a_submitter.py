# URN: test:govern-lifecycle:define-transition-autonomy:D020-UNIT-001-every-phase-declares-a-submitter
# Acceptance: acc:govern-lifecycle:D020-UNIT-001-every-phase-declares-a-submitter
# WMBT: wmbt:govern-lifecycle:D020
# Phase: GREEN
# Layer: unit
# Assertion: structural
"""D020-UNIT-001 — every phase declares who may SUBMIT its transition.

The axis must be TOTAL: the point of the declaration is that no phase is silent
about its submitter, because a silent phase is exactly the phase a worker stops
on. A partially-declared machine would be worse than none — it would read as
"declared" while still defaulting to asking.
"""
from __future__ import annotations

import pytest

from ._d020_autonomy import MACHINE_REL, PINNED, phases as _phases

pytestmark = [pytest.mark.coach, pytest.mark.platform]

#: The closed vocabulary. ``None`` is the machine's existing idiom for
#: "not applicable" — the same spelling ``agent: null`` already uses.
_VOCABULARY = {"agent", "operator", None}


@pytest.mark.platform
def test_every_phase_declares_the_autonomy_axis() -> None:
    """The axis is total — no phase is silent about who may submit."""
    phases = _phases()
    silent = sorted(name for name, spec in phases.items() if "autonomy" not in (spec or {}))
    assert not silent, (
        "REGRESSION: these phases declare no `autonomy` key, so the machine "
        f"still cannot say who may submit their transition: {silent}. "
        "GREEN adds one `autonomy` scalar per phase in "
        f"{MACHINE_REL}, beside the existing agent/transitions_to/pre_commit_gate."
    )


@pytest.mark.platform
def test_autonomy_values_come_from_the_closed_vocabulary() -> None:
    """A third value must not appear — the axis cannot quietly grow a mode."""
    phases = _phases()
    offenders = {
        name: (spec or {}).get("autonomy")
        for name, spec in phases.items()
        if "autonomy" in (spec or {}) and (spec or {}).get("autonomy") not in _VOCABULARY
    }
    assert not offenders, (
        f"`autonomy` values must be drawn from {sorted(v for v in _VOCABULARY if v)} "
        f"or null; found out-of-vocabulary values: {offenders}"
    )


@pytest.mark.platform
def test_declared_values_equal_the_pinned_table() -> None:
    """The declaration matches the decisions taken on #1626, INIT->PLANNED included."""
    phases = _phases()
    actual = {name: (spec or {}).get("autonomy") for name, spec in phases.items()}
    assert actual == PINNED, (
        "REGRESSION: the declared autonomy table does not match the table pinned "
        f"on #1626.\n  expected: {PINNED}\n  actual:   {actual}"
    )


@pytest.mark.platform
def test_terminal_phases_declare_autonomy_null() -> None:
    """A phase with no forward transition uses the machine's own null idiom."""
    phases = _phases()
    for name, spec in phases.items():
        spec = spec or {}
        if spec.get("transitions_to"):
            continue
        assert "autonomy" in spec, (
            f"terminal phase {name} declares no `autonomy` key; it must declare "
            "an explicit null, mirroring how it already declares `agent: null`"
        )
        assert spec["autonomy"] is None, (
            f"terminal phase {name} has no forward transition, so its `autonomy` "
            f"must be null, not {spec['autonomy']!r}"
        )


@pytest.mark.platform
def test_no_phase_is_autonomous_without_a_persona() -> None:
    """A phase with no agent has nobody who could submit autonomously."""
    phases = _phases()
    contradictions = sorted(
        name
        for name, spec in phases.items()
        if (spec or {}).get("autonomy") == "agent" and (spec or {}).get("agent") is None
    )
    assert not contradictions, (
        "these phases declare `autonomy: agent` while declaring `agent: null`, "
        f"so no persona exists to do the submitting: {contradictions}"
    )
