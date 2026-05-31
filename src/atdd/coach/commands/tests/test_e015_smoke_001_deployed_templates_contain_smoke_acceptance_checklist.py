# Acceptance: acc:spawn-agents:E015-SMOKE-001-deployed-templates-contain-smoke-acceptance-checklist
"""
E015 AC-SMOKE-001: The installed atdd package SESSION-LAUNCH-TEMPLATE.md ships
the planner.wmbt.must-have-smoke-acceptance rule id surfaced for spawn-time
agents, plus the validate command. CONDUCTOR.md no longer carries the rule id
(removed per #919 / #921 — the rule's canonical home is wmbt.convention.yaml,
and the installed-convention-ships-rule smoke check moved to
src/atdd/planner/validators/test_wmbt_smoke_acceptance_rule_registered.py).

This SMOKE test reads the templates from the actual installed package path
(not the local source tree) so it verifies that the content survives the
build-and-install pipeline that CI runs before executing the validate suite.

Convention: src/atdd/planner/conventions/wmbt.convention.yaml
            (rule planner.wmbt.must-have-smoke-acceptance)
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.slow]

RULE_ID = "planner.wmbt.must-have-smoke-acceptance"
VALIDATE_CMD = "atdd validate planner --local --skip-api"


def _installed_templates_dir() -> Path:
    templates_module = importlib.import_module("atdd.coach.templates")
    templates_dir = Path(templates_module.__file__).parent
    assert templates_dir.is_dir(), f"Installed templates dir not found: {templates_dir}"
    return templates_dir


def test_installed_session_launch_template_has_rule_id() -> None:
    """SESSION-LAUNCH-TEMPLATE.md from installed package contains the rule ID."""
    templates_dir = _installed_templates_dir()
    template_path = templates_dir / "SESSION-LAUNCH-TEMPLATE.md"
    assert template_path.exists(), f"Installed template not found: {template_path}"
    content = template_path.read_text()
    assert RULE_ID in content, (
        f"Installed SESSION-LAUNCH-TEMPLATE.md does not contain '{RULE_ID}'. "
        "The fix did not ship into the installed distribution."
    )


def test_installed_session_launch_template_has_validate_command() -> None:
    """SESSION-LAUNCH-TEMPLATE.md from installed package contains the validate command."""
    templates_dir = _installed_templates_dir()
    template_path = templates_dir / "SESSION-LAUNCH-TEMPLATE.md"
    content = template_path.read_text()
    assert VALIDATE_CMD in content, (
        f"Installed SESSION-LAUNCH-TEMPLATE.md does not contain '{VALIDATE_CMD}'. "
        "The pre-commit gate command did not ship into the installed distribution."
    )
