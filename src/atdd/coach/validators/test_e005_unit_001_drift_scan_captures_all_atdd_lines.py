# URN: test:govern-lifecycle:E005-UNIT-001-drift-scan-captures-all-atdd-lines
# Acceptance: acc:govern-lifecycle:E005-UNIT-001-drift-scan-captures-all-atdd-lines
# WMBT: wmbt:govern-lifecycle:E005
# Phase: RED
# Layer: backend.unit
# Assertion: structural

"""E005-UNIT-001 — the drift validator's scan helper captures every
``run: atdd ...`` line in an init-emitted workflow template as a STRUCTURED
invocation (subcommand token + remaining argument tokens), not just the
``run: atdd validate ...`` subset and not just raw strings.

Phase RED: fails — ``test_workflow_template_command_drift`` exposes only
``_extract_atdd_run_lines`` (returns raw strings); there is no
``extract_atdd_invocations`` helper yielding structured (subcommand, args)
records, so #481's coverage extension is not yet wired.

Phase GREEN: ``extract_atdd_invocations`` exists, returns one record per
``run: atdd ...`` line — validate AND non-validate alike — each exposing
its subcommand token and arg tokens, and excludes non-atdd ``run:`` lines.
"""

from __future__ import annotations

import pytest

import atdd.coach.validators.test_workflow_template_command_drift as drift

pytestmark = [pytest.mark.coach]


_TEMPLATE = """\
jobs:
  validate:
    steps:
      - name: planner
        run: atdd validate planner
      - name: auto-phase
        run: atdd auto-phase "$PR_NUMBER"
      - name: baseline
        run: atdd baseline update
      - name: install
        run: pip3 install atdd
"""


def _extract():
    """Return the structured-invocation helper or fail the RED test."""
    helper = getattr(drift, "extract_atdd_invocations", None)
    if helper is None:
        pytest.fail(
            "test_workflow_template_command_drift.extract_atdd_invocations is "
            "missing. E005-UNIT-001 requires a structured scan helper that "
            "captures every `run: atdd ...` line (validate AND non-validate)."
        )
    return helper


def test_scan_helper_exists() -> None:
    """A structured ``extract_atdd_invocations`` helper MUST be importable."""
    _extract()


def test_scan_captures_all_three_atdd_invocations() -> None:
    """validate, auto-phase, and baseline lines are ALL captured."""
    invocations = _extract()(_TEMPLATE)
    subcommands = [inv.subcommand for inv in invocations]
    assert subcommands == ["validate", "auto-phase", "baseline"], (
        f"Expected the scan helper to capture every `run: atdd ...` line "
        f"(validate, auto-phase, baseline). Got: {subcommands}."
    )


def test_scan_exposes_subcommand_and_arg_tokens() -> None:
    """Each captured invocation exposes its subcommand and remaining args."""
    invocations = _extract()(_TEMPLATE)
    by_sub = {inv.subcommand: inv for inv in invocations}
    assert by_sub["validate"].args == ["planner"], (
        f"validate invocation args wrong: {by_sub['validate'].args}"
    )
    assert by_sub["baseline"].args == ["update"], (
        f"baseline invocation args wrong: {by_sub['baseline'].args}"
    )


def test_scan_excludes_non_atdd_run_lines() -> None:
    """``run: pip3 install atdd`` is NOT an atdd invocation and is excluded."""
    invocations = _extract()(_TEMPLATE)
    subcommands = [inv.subcommand for inv in invocations]
    assert "install" not in subcommands and "pip3" not in subcommands, (
        f"Non-atdd `run:` lines must be excluded. Got: {subcommands}."
    )
