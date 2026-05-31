# URN: test:govern-lifecycle:freeze-coach-core-typed-api-and-phase-machine:E035-UNIT-002-phase-machine-yaml-is-canonical
# Acceptance: acc:govern-lifecycle:E035-UNIT-002-phase-machine-yaml-is-canonical
# WMBT: wmbt:govern-lifecycle:E035
# Phase: RED
# Layer: backend.integration
"""AC-UNIT-002 — ``phase_machine.convention.yaml`` is the canonical source of
phase transitions (matching docs/coach-decomposition.md §4.5), and the CLAUDE.md
managed block (and the CONDUCTOR.md template it is generated from) no longer carry a
duplicate ``state_machine.transitions`` mapping.

RED state: ``src/atdd/coach/conventions/phase_machine.convention.yaml`` does not
exist yet, and the CONDUCTOR.md template still contains a ``state_machine:`` block.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root

pytestmark = pytest.mark.coach

REPO_ROOT = find_repo_root()
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
PHASE_MACHINE_YAML = ATDD_PKG_DIR / "coach" / "conventions" / "phase_machine.convention.yaml"
ATDD_TEMPLATE = ATDD_PKG_DIR / "coach" / "templates" / "CONDUCTOR.md"

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


def test_claude_md_has_no_duplicate_state_machine_block():
    """The repo CLAUDE.md managed block must not carry a state_machine transition table."""
    claude_md = REPO_ROOT / "CLAUDE.md"
    text = claude_md.read_text()
    assert "state_machine:" not in text, (
        "CLAUDE.md still contains a state_machine transition table; "
        "phase_machine.convention.yaml is now the single source (§4.5)."
    )


def test_atdd_template_has_no_duplicate_state_machine_block():
    text = ATDD_TEMPLATE.read_text()
    assert "state_machine:" not in text, (
        "CONDUCTOR.md template still contains a state_machine transition table; "
        "remove it so CLAUDE.md regenerates without the duplicate (§4.5)."
    )
