# URN: test:govern-lifecycle:E005-UNIT-002-drift-validator-flags-unknown-subcommand
# Acceptance: acc:govern-lifecycle:E005-UNIT-002-drift-validator-flags-nonexistent-subcommand
# WMBT: wmbt:govern-lifecycle:E005
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""E005-UNIT-002 — the drift validator dispatches each captured invocation
through the live atdd top-level argparse and emits a Violation for any
subcommand the CLI does not declare (the ``atdd baseline`` blind spot).

Phase RED: fails — there is no ``evaluate_template_command_drift`` pure
evaluator accepting ``[(path, template_text)]``. The current scanner
(``scan_workflow_templates_for_cli_drift``) only flags ``rc=2`` +
``unrecognized arguments`` (flag-level drift); a bogus *subcommand*
produces ``invalid choice`` instead, so subcommand-level drift escapes.

Phase GREEN: ``evaluate_template_command_drift`` exists; a synthetic
template with ``run: atdd nonexistent-command`` yields exactly one
Violation with rule_id ``coach.workflow-template.command-must-parse``,
and a clean template yields ``[]``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import atdd.coach.validators.test_workflow_template_command_drift as drift

pytestmark = [pytest.mark.coach]

# Canonical id after the rule was renamed (#1225 removed the legacy monolith block
# that kept the old id `coach.workflow-template.command-must-parse`, now an alias on
# this single-node rule); bind_rule resolves the alias to this canonical id.
_RULE_ID = "coach.workspace.emitted-cli-must-parse"

_BOGUS_TEMPLATE = """\
jobs:
  validate:
    steps:
      - name: bogus
        run: atdd nonexistent-command --force
"""

_CLEAN_TEMPLATE = """\
jobs:
  validate:
    steps:
      - name: planner
        run: atdd validate planner
"""


def _evaluator():
    """Return the pure evaluator or fail the RED test."""
    fn = getattr(drift, "evaluate_template_command_drift", None)
    if fn is None:
        pytest.fail(
            "test_workflow_template_command_drift.evaluate_template_command_drift "
            "is missing. E005-UNIT-002 requires a pure evaluator that dispatches "
            "every captured `run: atdd ...` line through the live top-level "
            "argparse and flags unrecognized subcommands."
        )
    return fn


def test_evaluator_exists() -> None:
    """A pure ``evaluate_template_command_drift`` evaluator MUST be importable."""
    _evaluator()


def test_bogus_subcommand_yields_one_violation() -> None:
    """A ``run: atdd nonexistent-command`` line yields exactly one Violation."""
    violations = _evaluator()([(Path("atdd-validate.yml"), _BOGUS_TEMPLATE)])
    assert len(violations) == 1, (
        f"Expected exactly one Violation for the bogus subcommand line. "
        f"Got {len(violations)}: {violations}."
    )
    assert violations[0].rule_id == _RULE_ID, (
        f"Violation.rule_id should be {_RULE_ID!r}, got {violations[0].rule_id!r}."
    )
    assert "nonexistent-command" in violations[0].detail, (
        f"Violation.detail should name the offending invocation. "
        f"Got: {violations[0].detail!r}."
    )


def test_clean_template_yields_no_violation() -> None:
    """A template whose every atdd line parses cleanly yields ``[]``."""
    violations = _evaluator()([(Path("atdd-validate.yml"), _CLEAN_TEMPLATE)])
    assert violations == [], (
        f"A clean template must produce no Violations. Got: {violations}."
    )
