# URN: component:spawn-agents:E024:application
# Runtime: python
# Purpose: Validate that SESSION-LAUNCH-TEMPLATE.md contains the wagon-graph
#          section marker required by E022/E023.
"""Validator — coach.launch-prompt.must-include-wagon-graph (E024).

Checks that SESSION-LAUNCH-TEMPLATE.md contains '## Wagon Architecture' so
every spawned agent receives structural wagon context in its launch prompt.

Usage (direct):
    from atdd.coach.validators.launch_prompt_wagon_graph_guard import check_wagon_graph_rule
    violations = check_wagon_graph_rule(template_text)
    # Returns [] for a compliant template, or a list of violation strings.
"""
from __future__ import annotations

_RULE_ID = "coach.launch-prompt.must-include-wagon-graph"
_SECTION_MARKER = "## Wagon Architecture"


def check_wagon_graph_rule(template_content: str) -> list[str]:
    """Return violations if *template_content* lacks the wagon-graph section.

    Args:
        template_content: The full text of SESSION-LAUNCH-TEMPLATE.md (or a
            fixture string) to check.

    Returns:
        An empty list when the template is compliant (contains the section
        marker), or a list with one violation string describing the problem
        and referencing the rule ID.
    """
    if _SECTION_MARKER in template_content:
        return []

    violation = (
        f"[{_RULE_ID}] SESSION-LAUNCH-TEMPLATE.md is missing the "
        f"'{_SECTION_MARKER}' section. "
        f"E022/E023: add '## Wagon Architecture' with the wagon-graph slot "
        f"so agents receive structural wagon/graph context in their launch prompt. "
        f"See wmbt:spawn-agents:E022 and wmbt:spawn-agents:E023 for the injection "
        f"implementation (build_wagon_launch_prompt + _build_wagon_graph_section)."
    )
    return [violation]
