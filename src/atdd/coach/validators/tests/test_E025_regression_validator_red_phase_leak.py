# URN: test:govern-lifecycle:consumer-validator-scope-gate:E025-UNIT-004
# URN: test:govern-lifecycle:consumer-validator-scope-gate:E025-UNIT-005
# Acceptance: acc:govern-lifecycle:E025-UNIT-004-regression-validator-flags-red-phase-in-consumer-entrypoints
# Acceptance: acc:govern-lifecycle:E025-UNIT-005-regression-validator-passes-when-red-phase-has-platform-marker
# WMBT: wmbt:govern-lifecycle:E025
# Phase: RED
# Layer: unit
"""E025 — Regression validator: Phase:RED test files must have platform guard.

The regression validator scans consumer-facing validator entry point directories
and fails if any test file whose module docstring contains 'Phase: RED' can be
collected without a @pytest.mark.platform guard. This prevents future RED tests
from leaking into consumer runs.

The validator to be created:
  src/atdd/coach/validators/test_no_red_phase_tests_in_consumer_entry_points.py

The helper function to be tested:
  atdd.coach.validators.red_phase_leak_scanner.scan_for_red_phase_leaks(validator_dir)
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# ---------------------------------------------------------------------------
# The scanner module does not exist yet — these tests are Phase: RED.
# ---------------------------------------------------------------------------

_SCANNER_MODULE = "atdd.coach.validators.red_phase_leak_scanner"


def _import_scanner():
    """Import the scanner module; fail with an informative message if missing."""
    try:
        import importlib
        return importlib.import_module(_SCANNER_MODULE)
    except ImportError as exc:
        pytest.fail(
            f"Cannot import {_SCANNER_MODULE}: {exc}\n"
            "Phase: RED — this module must be created as part of E025 GREEN phase.\n"
            "Create: src/atdd/coach/validators/red_phase_leak_scanner.py\n"
            "Implement: scan_for_red_phase_leaks(validator_dir: Path) -> list[str]"
        )


# ---------------------------------------------------------------------------
# AC-UNIT-004: Scanner flags Phase:RED file WITHOUT platform marker
# ---------------------------------------------------------------------------


def test_scanner_flags_red_phase_file_without_platform_marker(tmp_path):
    """
    AC-UNIT-004: A test file with 'Phase: RED' in its module docstring and
    no @pytest.mark.platform decoration must be flagged as a violation.

    This is the exact pattern that caused the v3.81.1 regression: the file
    declared Phase:RED in its docstring but did not have a platform guard,
    so it was collected in consumer validator sweeps.
    """
    scanner = _import_scanner()

    # Create a synthetic test file that matches the offending pattern
    bad_file = tmp_path / "test_bad_red_phase.py"
    bad_file.write_text(textwrap.dedent('''\
        """
        Phase: RED — these tests FAIL on current main.
        Gate: GT-999
        """
        import pytest


        def test_something_that_will_fail():
            """This test has no platform guard and is Phase:RED."""
            assert False, "Not implemented yet"
    '''))

    violations = scanner.scan_for_red_phase_leaks(tmp_path)

    assert violations, (
        "scan_for_red_phase_leaks() must return a non-empty violation list "
        "when a Phase:RED test file has no @pytest.mark.platform guard.\n"
        f"Scanned dir: {tmp_path}\n"
        f"File: {bad_file}"
    )
    violation_text = "\n".join(violations)
    assert "test_bad_red_phase.py" in violation_text, (
        f"Violation list must reference the offending file name, got:\n{violation_text}"
    )


# ---------------------------------------------------------------------------
# AC-UNIT-005: Scanner passes when Phase:RED file HAS platform marker
# ---------------------------------------------------------------------------


def test_scanner_passes_red_phase_file_with_platform_marker(tmp_path):
    """
    AC-UNIT-005: A test file with 'Phase: RED' AND @pytest.mark.platform on
    every test function must produce zero violations.

    This is the corrected pattern: tests that target ATDD's own unshipped
    work are correctly gated so they don't run in consumer contexts.
    """
    scanner = _import_scanner()

    good_file = tmp_path / "test_good_red_phase.py"
    good_file.write_text(textwrap.dedent('''\
        """
        Phase: RED — these tests FAIL on current main.
        Gate: GT-010a
        """
        import pytest


        @pytest.mark.platform
        def test_something_correctly_guarded():
            """This test has a platform guard — excluded from consumer sweeps."""
            assert False, "Not implemented yet"
    '''))

    violations = scanner.scan_for_red_phase_leaks(tmp_path)

    assert not violations, (
        "scan_for_red_phase_leaks() must return an empty list when every "
        "test function in a Phase:RED file is decorated with @pytest.mark.platform.\n"
        f"Got violations:\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Edge: Non-RED files are not flagged even if they lack platform marker
# ---------------------------------------------------------------------------


def test_scanner_ignores_non_red_phase_files(tmp_path):
    """
    Edge case: A test file WITHOUT 'Phase: RED' and WITHOUT a platform marker
    must NOT be flagged. The scanner only cares about files that declare
    'Phase: RED' in their module docstring.
    """
    scanner = _import_scanner()

    consumer_file = tmp_path / "test_consumer_validator.py"
    consumer_file.write_text(textwrap.dedent('''\
        """Consumer-facing validator: checks plan/ wagon structure."""
        import pytest


        def test_wagon_has_description(repo_root):
            """This validator is consumer-facing with no platform restriction."""
            assert True
    '''))

    violations = scanner.scan_for_red_phase_leaks(tmp_path)

    assert not violations, (
        "Non-Phase:RED files must not be flagged by the scanner.\n"
        f"Got violations:\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Edge: Empty directory produces no violations
# ---------------------------------------------------------------------------


def test_scanner_tolerates_empty_directory(tmp_path):
    """Edge: scan_for_red_phase_leaks() on an empty dir returns []."""
    scanner = _import_scanner()

    violations = scanner.scan_for_red_phase_leaks(tmp_path)

    assert violations == [], (
        f"Empty directory must produce no violations, got: {violations}"
    )
