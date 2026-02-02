"""
Train First-Class Spec v0.6 Rollout Phase Controller.

Manages the phased rollout of train validation rules:
- Phase 1 (WARNINGS_ONLY): All new validators emit warnings only
- Phase 2 (BACKEND_ENFORCEMENT): Backend validators become strict
- Phase 3 (FULL_ENFORCEMENT): All validators become strict

Usage in validators:
    from atdd.coach.utils.train_spec_phase import TrainSpecPhase, should_enforce

    if should_enforce(TrainSpecPhase.BACKEND_ENFORCEMENT):
        assert condition, "Error message"
    else:
        if not condition:
            warnings.warn("Warning message")
"""

from enum import IntEnum
from typing import Optional
import warnings


class TrainSpecPhase(IntEnum):
    """
    Rollout phases for Train First-Class Spec v0.6.

    Phases are ordered by strictness level:
    - WARNINGS_ONLY (1): All new validators emit warnings, no assertions
    - BACKEND_ENFORCEMENT (2): Backend validators (0022-0025, 0031-0033) strict
    - FULL_ENFORCEMENT (3): All validators strict
    """
    WARNINGS_ONLY = 1
    BACKEND_ENFORCEMENT = 2
    FULL_ENFORCEMENT = 3


# Current rollout phase - update this to advance through phases
CURRENT_PHASE = TrainSpecPhase.WARNINGS_ONLY


def should_enforce(validator_phase: TrainSpecPhase) -> bool:
    """
    Check if a validator should enforce strict mode.

    Args:
        validator_phase: The phase at which this validator becomes strict

    Returns:
        True if current phase >= validator_phase (should enforce)
        False if current phase < validator_phase (should warn only)

    Example:
        # This validator becomes strict in Phase 2
        if should_enforce(TrainSpecPhase.BACKEND_ENFORCEMENT):
            assert backend_test_exists, "Backend test required"
        else:
            if not backend_test_exists:
                warnings.warn("Backend test missing (warning only)")
    """
    return CURRENT_PHASE >= validator_phase


def get_current_phase() -> TrainSpecPhase:
    """Get the current rollout phase."""
    return CURRENT_PHASE


def get_phase_name(phase: Optional[TrainSpecPhase] = None) -> str:
    """Get human-readable name for a phase."""
    phase = phase or CURRENT_PHASE
    return {
        TrainSpecPhase.WARNINGS_ONLY: "Phase 1: Warnings Only",
        TrainSpecPhase.BACKEND_ENFORCEMENT: "Phase 2: Backend Enforcement",
        TrainSpecPhase.FULL_ENFORCEMENT: "Phase 3: Full Enforcement",
    }.get(phase, "Unknown Phase")


def emit_phase_warning(
    spec_id: str,
    message: str,
    validator_phase: TrainSpecPhase = TrainSpecPhase.BACKEND_ENFORCEMENT
) -> None:
    """
    Emit a deprecation/validation warning with phase context.

    Args:
        spec_id: The SPEC ID (e.g., "SPEC-TRAIN-VAL-0022")
        message: The warning message
        validator_phase: Phase when this becomes an error
    """
    phase_name = get_phase_name(validator_phase)
    warnings.warn(
        f"[{spec_id}] {message} (will become error in {phase_name})",
        category=UserWarning,
        stacklevel=3
    )
