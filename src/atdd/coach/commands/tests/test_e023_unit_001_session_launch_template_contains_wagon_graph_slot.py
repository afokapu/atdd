# URN: test:spawn-agents:E023-UNIT-001-session-launch-template-contains-wagon-graph-slot
# Acceptance: acc:spawn-agents:E023-UNIT-001-session-launch-template-contains-wagon-graph-slot
# WMBT: wmbt:spawn-agents:E023
# Phase: RED
# Layer: unit
"""E023-UNIT-001 — SESSION-LAUNCH-TEMPLATE.md contains a wagon-graph section slot
and pre-flight step 5 instructing workers to re-run the graph command before
committing PLANNED.

Phase RED: fails because SESSION-LAUNCH-TEMPLATE.md does not yet contain the
'## Wagon Architecture' section heading, the 'atdd repo graph --wagon' pre-flight
instruction, or the 'before committing PLANNED' timing annotation.
Phase GREEN: all four assertions pass.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.spawn_agents]

_TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent  # src/atdd/coach/
    / "templates"
    / "SESSION-LAUNCH-TEMPLATE.md"
)

_WAGON_ARCH_HEADING = "## Wagon Architecture"
_GRAPH_CMD_REF = "atdd repo graph"
_WAGON_FLAG = "--wagon"
_PRE_FLIGHT_STEP_5 = "5."
_PLANNED_TIMING = "architectural drift"


def _read_template() -> str:
    assert _TEMPLATE_PATH.exists(), f"Template not found: {_TEMPLATE_PATH}"
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def test_template_has_wagon_architecture_heading() -> None:
    """SESSION-LAUNCH-TEMPLATE.md must contain '## Wagon Architecture'."""
    content = _read_template()
    assert _WAGON_ARCH_HEADING in content, (
        f"SESSION-LAUNCH-TEMPLATE.md does not contain '{_WAGON_ARCH_HEADING}'. "
        "E023: add a '## Wagon Architecture' section with the wagon-graph slot."
    )


def test_template_references_graph_command_with_wagon_flag() -> None:
    """The template must contain 'atdd repo graph' with '--wagon'."""
    content = _read_template()
    assert _GRAPH_CMD_REF in content, (
        f"SESSION-LAUNCH-TEMPLATE.md does not reference '{_GRAPH_CMD_REF}'. "
        "E023: pre-flight step 5 must instruct workers to run "
        "'atdd repo graph --wagon <wagon> --format launch-prompt'."
    )
    assert _WAGON_FLAG in content, (
        f"SESSION-LAUNCH-TEMPLATE.md references 'atdd repo graph' but not '{_WAGON_FLAG}'. "
        "E023: include the '--wagon' flag in the graph command reference."
    )


def test_template_has_pre_flight_step_5() -> None:
    """The template must contain a numbered step 5 in the pre-flight section."""
    content = _read_template()
    assert _PRE_FLIGHT_STEP_5 in content, (
        "SESSION-LAUNCH-TEMPLATE.md does not contain a numbered '5.' step. "
        "E023: add step 5 to the pre-flight checklist referencing the graph command."
    )


def test_template_includes_architectural_drift_annotation() -> None:
    """The wagon-graph instruction must mention 'architectural drift' as the risk it guards against.

    The WMBT says the step is specifically needed to 'catch architectural drift'.
    This phrase should appear near the graph command in the template.
    """
    content = _read_template()
    assert _PLANNED_TIMING in content, (
        "SESSION-LAUNCH-TEMPLATE.md does not contain 'architectural drift'. "
        "E023: the pre-flight step 5 must explain that re-running the graph command "
        "before committing PLANNED is needed to 'catch architectural drift'."
    )
