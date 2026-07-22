# URN: test:govern-lifecycle:coach-operator-safety-invariants:E065-UNIT-002-claude-md-retains-atdd-lifecycle-and-command-pointers
# Acceptance: acc:govern-lifecycle:E065-UNIT-002-claude-md-retains-atdd-lifecycle-and-command-pointers
# WMBT: wmbt:govern-lifecycle:E065
# Phase: RED
# Layer: backend.unit
# Assertion: structural
"""E023-UNIT-002 — slimmed CLAUDE.md retains the core lifecycle skeleton.

This is a regression guard test that ensures the E023 trim does NOT remove
the minimal orientation content workers need at session start:

* Every lifecycle phase declared in
  ``src/atdd/coach/conventions/phase_machine.convention.yaml`` — loaded
  dynamically, so adding a new phase to the convention auto-extends the
  regression guard and removing one auto-narrows it
* The ``atdd gate`` invocation (mandatory bootstrap step)
* A reference to the conventions directory (``src/atdd``)

#929: migrated the phase list from a hard-coded 6-name tuple to a dynamic
load of the convention YAML. Previously the test only enforced 6 of the 9
canonical phases (INIT, PLANNED, RED, GREEN, SMOKE, REFACTOR) — missing
COMPLETE, BLOCKED, OBSOLETE. The dynamic load mirrors the #921 / #925
pattern (template-content-reader → convention-reader) and prevents future
phase additions from silently bypassing the orientation regression guard.

Phase GREEN: passes — the trimmed CLAUDE.md retains every
convention-declared phase name plus the two bootstrap markers.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
import yaml

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
_PHASE_MACHINE_CONVENTION = (
    Path(__file__).parent.parent  # src/atdd/coach
    / "conventions"
    / "phase_machine.convention.yaml"
)

# Bootstrap markers that are NOT phase names — kept hard-coded because they
# are orientation breadcrumbs, not derived from a convention. If these names
# change, the test should explicitly track that change (the breadcrumbs are
# part of the operator contract).
_BOOTSTRAP_MARKERS: List[str] = [
    "atdd gate",
    "src/atdd",
]


def _required_phase_names() -> List[str]:
    """Load every phase NAME declared in phase_machine.convention.yaml.

    Returns the top-level keys under ``phases:`` (e.g. INIT, PLANNED, RED,
    GREEN, SMOKE, REFACTOR, COMPLETE, BLOCKED, OBSOLETE — whatever the
    canonical convention currently declares).
    """
    assert _PHASE_MACHINE_CONVENTION.exists(), (
        f"phase_machine convention not found: {_PHASE_MACHINE_CONVENTION}"
    )
    convention = yaml.safe_load(_PHASE_MACHINE_CONVENTION.read_text())
    phases = convention.get("phases")
    assert isinstance(phases, dict) and phases, (
        f"phase_machine.convention.yaml must declare a non-empty top-level "
        f"'phases:' mapping; got {type(phases).__name__}"
    )
    return sorted(phases.keys())


def test_claude_md_retains_atdd_lifecycle_and_command_pointers():
    """E023-UNIT-002: slimmed CLAUDE.md still contains all phase names + bootstrap markers."""
    assert CLAUDE_MD.exists(), f"CLAUDE.md not found at {CLAUDE_MD}"
    text = CLAUDE_MD.read_text(encoding="utf-8")

    phase_names = _required_phase_names()
    required = phase_names + _BOOTSTRAP_MARKERS

    missing = [s for s in required if s not in text]

    assert missing == [], (
        f"CLAUDE.md is missing {len(missing)} required orientation marker(s) "
        f"after slim:\n"
        + "\n".join(f"  - '{m}'" for m in missing)
        + "\n\nE023 requires the slimmed file to retain every lifecycle phase "
        "declared in src/atdd/coach/conventions/phase_machine.convention.yaml "
        f"(currently: {phase_names}), the 'atdd gate' invocation, and a "
        "reference to src/atdd/ conventions. Do not remove these markers "
        "when trimming the template."
    )
