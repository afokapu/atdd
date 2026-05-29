# URN: test:spawn-agents:E027-UNIT-002-wagon-graph-rule-fires-on-template-missing-section
# Acceptance: acc:spawn-agents:E027-UNIT-002-wagon-graph-rule-fires-on-template-missing-section
# WMBT: wmbt:spawn-agents:E027
# Phase: RED
# Layer: unit
"""E027-UNIT-002 — The coach.launch-prompt.must-include-wagon-graph validator fires
(reports at least one violation) when SESSION-LAUNCH-TEMPLATE.md lacks the
wagon-graph section marker.

Phase RED: fails because the validator module
`atdd.coach.validators.launch_prompt_wagon_graph_guard` does not yet exist
(ImportError).
Phase GREEN: module exists; check_wagon_graph_rule() returns a non-empty
violations list for a template missing the section marker.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.spawn_agents]

_RULE_ID = "coach.launch-prompt.must-include-wagon-graph"
_SECTION_MARKER = "## Wagon Architecture"

# Minimal template content that intentionally LACKS the wagon-graph section.
_TEMPLATE_WITHOUT_SECTION = textwrap.dedent("""\
    # ATDD Session Launch — Issue #{{issue_number}}

    ## Pre-flight

    1. Read CLAUDE.md.
    2. Run `atdd gate`.
    3. Run `atdd repo validate`.
    4. Run `gh issue view {{issue_number}}`.

    ## Issue context

    - **Number:** {{issue_number}}

    ## Workflow

    Follow the ATDD lifecycle strictly.
""")


def test_validator_fires_on_missing_section() -> None:
    """Validator must report at least one violation when section marker is absent."""
    from atdd.coach.validators.launch_prompt_wagon_graph_guard import (  # type: ignore[import]
        check_wagon_graph_rule,
    )

    violations = check_wagon_graph_rule(_TEMPLATE_WITHOUT_SECTION)
    assert violations, (
        f"Expected at least one violation from check_wagon_graph_rule when "
        f"'{_SECTION_MARKER}' is absent. Got 0 violations. "
        "E027: validator must fire for templates lacking the wagon-graph section."
    )


def test_violation_mentions_rule_id() -> None:
    """The violation message must reference the rule ID."""
    from atdd.coach.validators.launch_prompt_wagon_graph_guard import (  # type: ignore[import]
        check_wagon_graph_rule,
    )

    violations = check_wagon_graph_rule(_TEMPLATE_WITHOUT_SECTION)
    assert violations, "No violations returned — cannot check rule ID reference."

    violation_text = " ".join(str(v) for v in violations)
    assert _RULE_ID in violation_text, (
        f"Expected rule ID '{_RULE_ID}' in violation message. "
        f"Got: {violation_text!r}. "
        "E027: violation must be addressable by rule ID."
    )


def test_violation_contains_remediation_hint() -> None:
    """The violation must contain a remediation hint referencing E025 or E026."""
    from atdd.coach.validators.launch_prompt_wagon_graph_guard import (  # type: ignore[import]
        check_wagon_graph_rule,
    )

    violations = check_wagon_graph_rule(_TEMPLATE_WITHOUT_SECTION)
    assert violations, "No violations returned — cannot check remediation hint."

    violation_text = " ".join(str(v) for v in violations).lower()
    assert any(kw in violation_text for kw in ("e022", "e023", "wagon", "graph")), (
        "Expected remediation hint referencing E025, E026, 'wagon', or 'graph' "
        f"in violation message. Got: {violation_text!r}. "
        "E027: hint must guide the fixer to the relevant WMBT."
    )
