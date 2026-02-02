"""
ATDD Hierarchy Coverage Spec v0.1 Rollout Phase Controller.

Manages the phased rollout of coverage validation rules:
- Phase 1 (WARNINGS_ONLY): All validators emit warnings only
- Phase 2 (PLANNER_TESTER_ENFORCEMENT): Sections 2 + 3 validators strict
- Phase 3 (FULL_ENFORCEMENT): All validators (including Section 4) strict

Usage in validators:
    from atdd.coach.utils.coverage_phase import CoveragePhase, should_enforce

    if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
        assert condition, "Error message"
    else:
        if not condition:
            emit_coverage_warning("COVERAGE-PLAN-2.1", "Warning message", CoveragePhase.PLANNER_TESTER_ENFORCEMENT)
"""

from enum import IntEnum
from typing import Optional
import warnings


class CoveragePhase(IntEnum):
    """
    Rollout phases for ATDD Hierarchy Coverage Spec v0.1.

    Phases are ordered by strictness level:
    - WARNINGS_ONLY (1): All new validators emit warnings, no assertions
    - PLANNER_TESTER_ENFORCEMENT (2): Planner (Section 2) + Tester (Section 3) strict
    - FULL_ENFORCEMENT (3): All validators including Coder (Section 4) strict
    """
    WARNINGS_ONLY = 1
    PLANNER_TESTER_ENFORCEMENT = 2
    FULL_ENFORCEMENT = 3


# Current rollout phase - update this to advance through phases
CURRENT_PHASE = CoveragePhase.WARNINGS_ONLY


def should_enforce(validator_phase: CoveragePhase) -> bool:
    """
    Check if a validator should enforce strict mode.

    Args:
        validator_phase: The phase at which this validator becomes strict

    Returns:
        True if current phase >= validator_phase (should enforce)
        False if current phase < validator_phase (should warn only)

    Example:
        # This validator becomes strict in Phase 2
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            assert wagon_in_train, "Wagon must be in at least one train"
        else:
            if not wagon_in_train:
                emit_coverage_warning("COVERAGE-PLAN-2.1", "Wagon not in any train", CoveragePhase.PLANNER_TESTER_ENFORCEMENT)
    """
    return CURRENT_PHASE >= validator_phase


def get_current_phase() -> CoveragePhase:
    """Get the current rollout phase."""
    return CURRENT_PHASE


def get_phase_name(phase: Optional[CoveragePhase] = None) -> str:
    """Get human-readable name for a phase."""
    phase = phase or CURRENT_PHASE
    return {
        CoveragePhase.WARNINGS_ONLY: "Phase 1: Warnings Only",
        CoveragePhase.PLANNER_TESTER_ENFORCEMENT: "Phase 2: Planner+Tester Enforcement",
        CoveragePhase.FULL_ENFORCEMENT: "Phase 3: Full Enforcement",
    }.get(phase, "Unknown Phase")


def emit_coverage_warning(
    spec_id: str,
    message: str,
    validator_phase: CoveragePhase = CoveragePhase.PLANNER_TESTER_ENFORCEMENT
) -> None:
    """
    Emit a coverage validation warning with phase context.

    Args:
        spec_id: The SPEC ID (e.g., "COVERAGE-PLAN-2.1")
        message: The warning message
        validator_phase: Phase when this becomes an error
    """
    phase_name = get_phase_name(validator_phase)
    warnings.warn(
        f"[{spec_id}] {message} (will become error in {phase_name})",
        category=UserWarning,
        stacklevel=3
    )
