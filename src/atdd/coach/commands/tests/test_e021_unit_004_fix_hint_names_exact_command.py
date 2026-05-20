# URN: test:govern-lifecycle:systemic-registry-drift-enforcement:E021-UNIT-004-fix-hint-names-exact-command
# Acceptance: acc:govern-lifecycle:E021-UNIT-004-fix-hint-names-exact-command
# WMBT: wmbt:govern-lifecycle:E021
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-004: When the registry check fails, format_fix_hint(drift_report) returns
a string containing 'atdd registry update --yes' and the names of drifted files,
suitable for printing directly to stderr in the hook or CI step.

RED state: format_fix_hint() and RegistryDriftError do not exist in
atdd.coach.commands.registry. This test fails with an import-level assertion
until they are implemented.
"""
from __future__ import annotations

import pytest

# Stub imports — these don't exist yet; tests assert their existence.
try:
    from atdd.coach.commands.registry import format_fix_hint  # type: ignore[attr-defined]
    _HAS_FORMAT_FIX_HINT = True
except ImportError:
    format_fix_hint = None  # type: ignore[assignment]
    _HAS_FORMAT_FIX_HINT = False

try:
    from atdd.coach.commands.registry import RegistryDriftError  # type: ignore[attr-defined]
    _HAS_DRIFT_ERROR = True
except ImportError:
    RegistryDriftError = None  # type: ignore[assignment]
    _HAS_DRIFT_ERROR = False


def test_format_fix_hint_function_exists():
    """format_fix_hint() must be importable from atdd.coach.commands.registry."""
    assert _HAS_FORMAT_FIX_HINT, (
        "format_fix_hint not found in atdd.coach.commands.registry. "
        "Implement format_fix_hint(drift_report: dict) -> str."
    )


def test_registry_drift_error_exists():
    """RegistryDriftError must be importable from atdd.coach.commands.registry."""
    assert _HAS_DRIFT_ERROR, (
        "RegistryDriftError not found in atdd.coach.commands.registry. "
        "Implement RegistryDriftError as an Exception subclass with a drift_report attribute."
    )


def test_fix_hint_contains_exact_remediation_command():
    """format_fix_hint() output must contain 'atdd registry update --yes'."""
    assert _HAS_FORMAT_FIX_HINT, "format_fix_hint not implemented"
    drift_report = {
        "drifted_files": ["plan/_wagons.yaml", "plan/_trains.yaml"],
        "wagons": ["govern-lifecycle", "spawn-agents"],
    }
    hint = format_fix_hint(drift_report)
    assert "atdd registry update --yes" in hint, (
        f"fix hint must contain 'atdd registry update --yes'. Got:\n{hint}"
    )


def test_fix_hint_names_drifted_files():
    """format_fix_hint() output must mention each drifted file name."""
    assert _HAS_FORMAT_FIX_HINT, "format_fix_hint not implemented"
    drift_report = {
        "drifted_files": ["plan/_wagons.yaml", "contracts/_artifacts.yaml"],
    }
    hint = format_fix_hint(drift_report)
    assert "plan/_wagons.yaml" in hint, (
        f"fix hint must name drifted file 'plan/_wagons.yaml'. Got:\n{hint}"
    )
    assert "contracts/_artifacts.yaml" in hint, (
        f"fix hint must name drifted file 'contracts/_artifacts.yaml'. Got:\n{hint}"
    )


def test_fix_hint_is_nonempty_string():
    """format_fix_hint() must return a non-empty string."""
    assert _HAS_FORMAT_FIX_HINT, "format_fix_hint not implemented"
    drift_report = {"drifted_files": ["plan/_wagons.yaml"]}
    hint = format_fix_hint(drift_report)
    assert isinstance(hint, str) and len(hint) > 0, (
        f"format_fix_hint must return a non-empty string, got: {hint!r}"
    )


def test_fix_hint_suitable_for_stderr(capsys):
    """format_fix_hint() output can be printed to stderr without error."""
    assert _HAS_FORMAT_FIX_HINT, "format_fix_hint not implemented"
    import sys
    drift_report = {"drifted_files": ["plan/_wagons.yaml"]}
    hint = format_fix_hint(drift_report)
    print(hint, file=sys.stderr)
    captured = capsys.readouterr()
    assert len(captured.err) > 0, "Expected non-empty stderr output from fix hint"
