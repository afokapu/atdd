"""
Localization Manifest Spec v1 Rollout Phase Controller.

Manages the phased rollout of localization validation rules:
- Phase 1 (WARNINGS_ONLY): All validators emit warnings only
- Phase 2 (TESTER_ENFORCEMENT): Tester phase validators (LOCALE-TEST-*) strict
- Phase 3 (FULL_ENFORCEMENT): All validators including Coder (LOCALE-CODE-*) strict

Usage in validators:
    from atdd.coach.utils.locale_phase import LocalePhase, should_enforce_locale

    if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
        assert condition, "Error message"
    else:
        if not condition:
            emit_locale_warning("LOCALE-TEST-1.1", "Warning message", LocalePhase.TESTER_ENFORCEMENT)
"""

from enum import IntEnum
from typing import Optional
import warnings


class LocalePhase(IntEnum):
    """
    Rollout phases for Localization Manifest Spec v1.

    Phases are ordered by strictness level:
    - WARNINGS_ONLY (1): All new validators emit warnings, no assertions
    - TESTER_ENFORCEMENT (2): Tester phase validators (LOCALE-TEST-*) strict
    - FULL_ENFORCEMENT (3): All validators including Coder (LOCALE-CODE-*) strict
    """
    WARNINGS_ONLY = 1
    TESTER_ENFORCEMENT = 2
    FULL_ENFORCEMENT = 3


# Current rollout phase - update this to advance through phases
CURRENT_LOCALE_PHASE = LocalePhase.WARNINGS_ONLY


def should_enforce_locale(validator_phase: LocalePhase) -> bool:
    """
    Check if a locale validator should enforce strict mode.

    Args:
        validator_phase: The phase at which this validator becomes strict

    Returns:
        True if current phase >= validator_phase (should enforce)
        False if current phase < validator_phase (should warn only)

    Example:
        # This validator becomes strict in Phase 2
        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            assert all_keys_match, "Keys must match reference locale"
        else:
            if not all_keys_match:
                emit_locale_warning("LOCALE-TEST-1.4", "Keys don't match", LocalePhase.TESTER_ENFORCEMENT)
    """
    return CURRENT_LOCALE_PHASE >= validator_phase


def get_current_locale_phase() -> LocalePhase:
    """Get the current locale rollout phase."""
    return CURRENT_LOCALE_PHASE


def get_locale_phase_name(phase: Optional[LocalePhase] = None) -> str:
    """Get human-readable name for a locale phase."""
    phase = phase or CURRENT_LOCALE_PHASE
    return {
        LocalePhase.WARNINGS_ONLY: "Phase 1: Warnings Only",
        LocalePhase.TESTER_ENFORCEMENT: "Phase 2: Tester Enforcement",
        LocalePhase.FULL_ENFORCEMENT: "Phase 3: Full Enforcement",
    }.get(phase, "Unknown Phase")


def emit_locale_warning(
    spec_id: str,
    message: str,
    validator_phase: LocalePhase = LocalePhase.TESTER_ENFORCEMENT
) -> None:
    """
    Emit a locale validation warning with phase context.

    Args:
        spec_id: The SPEC ID (e.g., "LOCALE-TEST-1.1")
        message: The warning message
        validator_phase: Phase when this becomes an error
    """
    phase_name = get_locale_phase_name(validator_phase)
    warnings.warn(
        f"[{spec_id}] {message} (will become error in {phase_name})",
        category=UserWarning,
        stacklevel=3
    )
