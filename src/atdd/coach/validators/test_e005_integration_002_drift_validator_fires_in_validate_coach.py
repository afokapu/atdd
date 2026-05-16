# URN: test:govern-lifecycle:E005-INTEGRATION-002-drift-validator-fires-in-validate-coach
# Acceptance: acc:govern-lifecycle:E005-INTEGRATION-002-drift-validator-fires-in-validate-coach
# WMBT: wmbt:govern-lifecycle:E005
# Phase: RED
# Layer: backend.integration
# Assertion: behavioral

"""E005-INTEGRATION-002 — the widened drift validator (the one the coach
suite runs) fails when an init-emitted template carries a subcommand-level
drift that the #473-phase-3 ``unrecognized arguments`` check would miss.

Phase RED: fails — there is no ``evaluate_template_command_drift`` pure
evaluator, so the coach suite cannot be driven against a fixture workflow
that contains a ``run: atdd baseline update`` line. The existing
``scan_workflow_templates_for_cli_drift`` only flags ``unrecognized
arguments`` (flag drift), so a bogus *subcommand* (``invalid choice``)
passes through silently.

Phase GREEN: ``evaluate_template_command_drift`` flags the
``atdd baseline update`` line — the coach suite then exits non-zero — and
the same fixture with the baseline-sync drift removed passes clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import atdd.coach.validators.test_workflow_template_command_drift as drift

pytestmark = [pytest.mark.coach]

_VALIDATE_YML = Path(".github/workflows/atdd-validate.yml")

_DRIFTED = """\
jobs:
  baseline-sync:
    steps:
      - name: Update baselines
        run: atdd baseline update
"""

_CLEAN = """\
jobs:
  validate:
    steps:
      - name: coach
        run: atdd validate coach --skip-api
"""


def _evaluator():
    """Return the pure evaluator the coach suite drives, or fail the RED test."""
    fn = getattr(drift, "evaluate_template_command_drift", None)
    if fn is None:
        pytest.fail(
            "test_workflow_template_command_drift.evaluate_template_command_drift "
            "is missing. E005-INTEGRATION-002 requires the coach-suite drift "
            "validator to flag subcommand-level drift in init-emitted templates."
        )
    return fn


def test_coach_suite_fails_on_baseline_subcommand_drift() -> None:
    """A fixture atdd-validate.yml with ``atdd baseline update`` fails the suite."""
    violations = _evaluator()([(_VALIDATE_YML, _DRIFTED)])
    assert len(violations) >= 1, (
        "The coach drift validator must flag the `atdd baseline update` line — "
        "`baseline` is not a top-level subcommand (invalid choice). "
        f"Got no violations: {violations}."
    )
    detail = violations[0].detail
    location = getattr(violations[0], "location", "") or ""
    assert "baseline" in detail, (
        f"Violation.detail must name the offending invocation. Got: {detail!r}."
    )
    assert "atdd-validate.yml" in (detail + location), (
        f"Violation must identify the atdd-validate.yml path. "
        f"detail={detail!r} location={location!r}."
    )


def test_coach_suite_passes_when_drift_removed() -> None:
    """The same fixture with the baseline-sync drift removed passes clean."""
    violations = _evaluator()([(_VALIDATE_YML, _CLEAN)])
    assert violations == [], (
        f"A fixture with no subcommand drift must pass the coach drift "
        f"validator. Got: {violations}."
    )
