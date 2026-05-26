# Acceptance: acc:spawn-agents:E015-UNIT-001-session-launch-template-names-must-have-smoke-acceptance-rule
"""
E015 AC-UNIT-001: SESSION-LAUNCH-TEMPLATE.md contains a pre-commit gate section
that names planner.wmbt.must-have-smoke-acceptance and the command
atdd validate planner --local --skip-api.

The template is the primary context an agent reads when spawned into a planning
session. Surfacing the rule by name — with the exact validator command — prevents
the recurring pattern where planners commit PLANNED without SMOKE acceptances and
CI flags the violation too late to avoid operator-intervention cycles.

Convention: src/atdd/planner/conventions/wmbt.convention.yaml
            (rule planner.wmbt.must-have-smoke-acceptance)
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

RULE_ID = "planner.wmbt.must-have-smoke-acceptance"
VALIDATE_CMD = "atdd validate planner --local --skip-api"


def _read_template() -> str:
    assert _TEMPLATE_PATH.exists(), f"Template not found: {_TEMPLATE_PATH}"
    return _TEMPLATE_PATH.read_text()


def test_template_names_must_have_smoke_acceptance_rule() -> None:
    """The rule ID 'planner.wmbt.must-have-smoke-acceptance' appears in the template."""
    content = _read_template()
    assert RULE_ID in content, (
        f"SESSION-LAUNCH-TEMPLATE.md does not contain the rule ID '{RULE_ID}'. "
        "Add a Planner pre-commit gate section naming this rule before the RED workflow step."
    )


def test_template_includes_validate_planner_command() -> None:
    """The command 'atdd validate planner --local --skip-api' appears in the template."""
    content = _read_template()
    assert VALIDATE_CMD in content, (
        f"SESSION-LAUNCH-TEMPLATE.md does not contain the validator command '{VALIDATE_CMD}'. "
        "The pre-commit gate section must instruct the agent to run this command before committing PLANNED."
    )


def test_template_references_smoke_in_planned_context() -> None:
    """The template contains 'SMOKE' in proximity to 'committing PLANNED' context."""
    content = _read_template()
    assert "SMOKE" in content, (
        "SESSION-LAUNCH-TEMPLATE.md does not reference SMOKE at all. "
        "The pre-commit gate section must mention SMOKE acceptances as the requirement."
    )
    # The SMOKE reference must be in a planner / PLANNED context, not just in the
    # existing 'SMOKE — verify against real infrastructure' workflow step.
    assert "PLANNED" in content or "planner" in content.lower(), (
        "SESSION-LAUNCH-TEMPLATE.md does not have a PLANNED / planner context for the SMOKE reference. "
        "Add a pre-commit gate section that ties SMOKE acceptance requirement to the PLANNED commit."
    )
