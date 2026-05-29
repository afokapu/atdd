# URN: test:spawn-agents:E027-UNIT-003-wagon-graph-rule-passes-on-compliant-template
# Acceptance: acc:spawn-agents:E027-UNIT-003-wagon-graph-rule-passes-on-compliant-template
# WMBT: wmbt:spawn-agents:E027
# Phase: RED
# Layer: unit
"""E027-UNIT-003 — The coach.launch-prompt.must-include-wagon-graph validator
reports zero violations when SESSION-LAUNCH-TEMPLATE.md contains the
wagon-graph section marker.

Phase RED: fails because the validator module
`atdd.coach.validators.launch_prompt_wagon_graph_guard` does not yet exist
(ImportError).
Phase GREEN: module exists; check_wagon_graph_rule() returns an empty list
for a compliant template containing '## Wagon Architecture'.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.spawn_agents]

_SECTION_MARKER = "## Wagon Architecture"

# Minimal template that contains the wagon-graph section marker.
_COMPLIANT_TEMPLATE = textwrap.dedent("""\
    # ATDD Session Launch — Issue #{{issue_number}}

    ## Pre-flight

    1. Read CLAUDE.md.
    2. Run `atdd gate`.
    3. Run `atdd repo validate`.
    4. Run `gh issue view {{issue_number}}`.
    5. Run `atdd repo graph --wagon {{wagon}} --format launch-prompt` to see the
       wagon architecture (re-run before committing PLANNED to catch architectural drift).

    ## Wagon Architecture

    {{wagon_graph_section}}

    ## Issue context

    - **Number:** {{issue_number}}

    ## Workflow

    Follow the ATDD lifecycle strictly.
""")


def test_validator_passes_on_compliant_template() -> None:
    """check_wagon_graph_rule() must return zero violations for a compliant template."""
    from atdd.coach.validators.launch_prompt_wagon_graph_guard import (  # type: ignore[import]
        check_wagon_graph_rule,
    )

    violations = check_wagon_graph_rule(_COMPLIANT_TEMPLATE)
    assert not violations, (
        f"Expected zero violations for a template containing '{_SECTION_MARKER}'. "
        f"Got {len(violations)} violation(s):\n"
        + "\n".join(str(v) for v in violations)
    )


def test_validator_passes_on_actual_template_after_e023() -> None:
    """check_wagon_graph_rule() must pass on the actual SESSION-LAUNCH-TEMPLATE.md
    after E026 has been applied (i.e. the real template contains the section marker).
    """
    from atdd.coach.validators.launch_prompt_wagon_graph_guard import (  # type: ignore[import]
        check_wagon_graph_rule,
    )

    template_path = (
        Path(__file__).parent.parent.parent  # src/atdd/coach/
        / "templates"
        / "SESSION-LAUNCH-TEMPLATE.md"
    )
    assert template_path.exists(), f"Template not found: {template_path}"
    content = template_path.read_text(encoding="utf-8")

    violations = check_wagon_graph_rule(content)
    assert not violations, (
        f"Expected zero violations on SESSION-LAUNCH-TEMPLATE.md but got "
        f"{len(violations)} violation(s):\n"
        + "\n".join(str(v) for v in violations)
        + "\nE026: add the '## Wagon Architecture' section to the template."
    )
