# URN: test:govern-lifecycle:E005-SMOKE-001-real-validate-coach-runs-extended-drift-validator
# Acceptance: acc:govern-lifecycle:E005-SMOKE-001-real-validate-coach-runs-extended-drift-validator
# WMBT: wmbt:govern-lifecycle:E005
# Phase: RED
# Layer: backend.smoke
# Assertion: behavioral

"""E005-SMOKE-001 — against REAL infrastructure (the real ``ProjectInitializer``
emit + the live ``python -m atdd`` argparse), the extended drift validator
scans every ``run: atdd ...`` line — validate AND non-validate alike — and
catches subcommand-level drift, not just ``unrecognized arguments`` flag drift.

Phase RED: fails — there is no directory-scanning entry point
(``scan_workflow_dir_for_command_drift``) that the coach suite can run over
real-emitted workflow files; the existing ``scan_workflow_templates_for_cli_drift``
only flags ``rc=2`` + ``unrecognized arguments``, so a bogus *subcommand*
(``invalid choice``) in a real workflow file is reported clean.

Phase GREEN: the extended scanner walks every emitted workflow file, feeds
every ``run: atdd ...`` line through the live argparse, and flags any line
whose subcommand the CLI does not declare.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import atdd.coach.validators.test_workflow_template_command_drift as drift

pytestmark = [pytest.mark.coach]


def _dir_scanner():
    """Return the real directory-scanning drift entry point, or fail the RED test."""
    fn = getattr(drift, "scan_workflow_dir_for_command_drift", None)
    if fn is None:
        pytest.fail(
            "test_workflow_template_command_drift.scan_workflow_dir_for_command_drift "
            "is missing. E005-SMOKE-001 requires a real entry point that scans "
            "every emitted workflow file for subcommand-level CLI drift."
        )
    return fn


def test_extended_validator_catches_subcommand_drift_in_real_emit() -> None:
    """Real initializer emit + an injected bogus subcommand → flagged by the
    extended validator against the live argparse."""
    scan = _dir_scanner()
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)
        # REAL infrastructure: drive the actual ProjectInitializer emit.
        emitted = drift._emit_workflow_files(target)
        assert emitted, "ProjectInitializer emitted no workflow files."
        workflows_dir = emitted[0].parent

        # Inject a deliberately-bogus NON-validate subcommand into a real file.
        victim = emitted[0]
        victim.write_text(
            victim.read_text()
            + "\n      - name: bogus\n        run: atdd definitely-not-a-subcommand\n"
        )

        violations = scan(workflows_dir)
        assert any(
            "definitely-not-a-subcommand" in v.detail for v in violations
        ), (
            "The extended drift validator must scan non-validate `run: atdd ...` "
            "lines in real-emitted workflow files and flag subcommand-level drift "
            f"against the live argparse. Got violations: {violations}."
        )


def test_extended_validator_passes_clean_real_emit() -> None:
    """A pristine real initializer emit (no injected drift) reports clean."""
    scan = _dir_scanner()
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)
        emitted = drift._emit_workflow_files(target)
        workflows_dir = emitted[0].parent
        violations = scan(workflows_dir)
        # Pristine emit must be clean once the baseline-sync drift is retired.
        assert violations == [], (
            f"A pristine real initializer emit must pass the extended drift "
            f"validator. Got: {violations}."
        )
