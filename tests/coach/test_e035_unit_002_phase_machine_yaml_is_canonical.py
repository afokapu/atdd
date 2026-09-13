# URN: test:govern-lifecycle:freeze-coach-core-typed-api-and-phase-machine:E035-UNIT-002-phase-machine-yaml-is-canonical
# Acceptance: acc:govern-lifecycle:E035-UNIT-002-phase-machine-yaml-is-canonical
# WMBT: wmbt:govern-lifecycle:E035
# Phase: RED
# Layer: backend.integration
"""AC-UNIT-002 — ``phase_machine.convention.yaml`` is the canonical source of
phase transitions, matching docs/coach-decomposition.md §4.5.

It was also the single source of truth *relative to* the CLAUDE.md managed block and
the CONDUCTOR.md template it was generated from. Both were deleted (#1811/#1812/#1941),
so that half of the acceptance is satisfied by construction (#1979).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import atdd

pytestmark = pytest.mark.coach

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
PHASE_MACHINE_YAML = ATDD_PKG_DIR / "coach" / "conventions" / "phase_machine.convention.yaml"

# §4.5 canonical data.
EXPECTED = {
    "INIT": {"agent": "planner",
             "transitions_to": ["PLANNED", "BLOCKED", "OBSOLETE"],
             "pre_commit_gate": "atdd validate planner --local --skip-api"},
    "PLANNED": {"agent": "tester", "transitions_to": ["RED", "BLOCKED", "OBSOLETE"]},
    "RED": {"agent": "coder", "transitions_to": ["GREEN", "BLOCKED", "OBSOLETE"]},
    "GREEN": {"agent": "tester", "transitions_to": ["SMOKE", "BLOCKED", "OBSOLETE"]},
    "SMOKE": {"agent": "coder", "transitions_to": ["REFACTOR", "BLOCKED", "OBSOLETE"]},
    "REFACTOR": {"agent": "coder", "transitions_to": ["COMPLETE", "BLOCKED", "OBSOLETE"]},
    "COMPLETE": {"agent": None, "transitions_to": []},
    "BLOCKED": {"agent": None,
                "transitions_to": ["INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "OBSOLETE"]},
    "OBSOLETE": {"agent": None, "transitions_to": []},
}


def _load_phases() -> dict:
    data = yaml.safe_load(PHASE_MACHINE_YAML.read_text())
    return data["phases"]


def test_phase_machine_yaml_exists():
    assert PHASE_MACHINE_YAML.exists(), f"missing {PHASE_MACHINE_YAML}"


def test_phase_machine_declares_all_nine_phases():
    phases = _load_phases()
    assert set(phases) == set(EXPECTED)


@pytest.mark.parametrize("phase", sorted(EXPECTED))
def test_phase_machine_transitions_and_agent_match_spec(phase: str):
    spec = _load_phases()[phase]
    expected = EXPECTED[phase]
    assert spec.get("agent") == expected["agent"]
    assert list(spec.get("transitions_to")) == expected["transitions_to"]


def test_init_carries_pre_commit_gate():
    init = _load_phases()["INIT"]
    assert init.get("pre_commit_gate") == "atdd validate planner --local --skip-api"


# The two tests that stood here asserted that the CLAUDE.md managed block and the
# CONDUCTOR.md template carried no duplicate `state_machine:` mapping. #1811 retired
# the agent-config projection, #1812 deleted the CONDUCTOR.md template and #1941
# deleted CLAUDE.md, so the duplicate source this acceptance guards against cannot
# exist: phase_machine.convention.yaml is the only remaining declaration (#1979).
# Both tests had been failing on `read_text()` of a deleted path — they asserted
# nothing about the invariant, they just errored.
