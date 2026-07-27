# URN: test:govern-lifecycle:define-transition-autonomy:D020-UNIT-001-every-phase-declares-a-submitter
# Acceptance: acc:govern-lifecycle:D020-UNIT-001-every-phase-declares-a-submitter
# WMBT: wmbt:govern-lifecycle:D020
# Phase: RED
# Layer: unit
# Assertion: structural
"""D020-UNIT-001 — every phase declares who may SUBMIT its transition.

Phase: RED. The ``autonomy`` axis does not exist in
``src/atdd/coach/conventions/phase_machine.convention.yaml`` yet, so every
assertion below fails on the absent key. GREEN adds one scalar per phase.

The axis must be TOTAL: the point of the declaration is that no phase is silent
about its submitter, because a silent phase is exactly the phase a worker stops
on. A partially-declared machine would be worse than none — it would read as
"declared" while still defaulting to asking.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.platform]

_MACHINE_REL = Path("src/atdd/coach/conventions/phase_machine.convention.yaml")

#: The closed vocabulary. ``None`` is the machine's existing idiom for
#: "not applicable" — the same spelling ``agent: null`` already uses.
_VOCABULARY = {"agent", "operator", None}

#: The table pinned by the operator on #1626. Phases with no forward transition
#: carry None.
_PINNED = {
    "INIT": "operator",
    "PLANNED": "operator",
    "RED": "agent",
    "GREEN": "agent",
    "SMOKE": "agent",
    "REFACTOR": "operator",
    "COMPLETE": None,
    "BLOCKED": "operator",
    "OBSOLETE": None,
}


def _phases() -> dict:
    path = find_repo_root() / _MACHINE_REL
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    phases = data.get("phases") or {}
    assert phases, f"{_MACHINE_REL} declares no phases:"
    return phases


@pytest.mark.platform
def test_every_phase_declares_the_autonomy_axis() -> None:
    """The axis is total — no phase is silent about who may submit."""
    phases = _phases()
    silent = sorted(name for name, spec in phases.items() if "autonomy" not in (spec or {}))
    assert not silent, (
        "Phase: RED — these phases declare no `autonomy` key, so the machine "
        f"still cannot say who may submit their transition: {silent}. "
        "GREEN adds one `autonomy` scalar per phase in "
        f"{_MACHINE_REL}, beside the existing agent/transitions_to/pre_commit_gate."
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
    assert actual == _PINNED, (
        "Phase: RED — the declared autonomy table does not match the table pinned "
        f"on #1626.\n  expected: {_PINNED}\n  actual:   {actual}"
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
