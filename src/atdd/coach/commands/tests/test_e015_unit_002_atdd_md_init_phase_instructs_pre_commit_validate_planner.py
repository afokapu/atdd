# Acceptance: acc:spawn-agents:E015-UNIT-002-atdd-md-init-phase-instructs-pre-commit-validate-planner
"""
E015 AC-UNIT-002: CONDUCTOR.md template INIT phase block surfaces the
pre-commit validate command and its 'BEFORE committing PLANNED' timing.

CONDUCTOR.md is the persistent instruction file installed in every worktree via
atdd sync. The INIT phase block carries operator-facing instructions that
belong in the template (the command name + the timing annotation). It does NOT
carry the planner.wmbt.must-have-smoke-acceptance rule id itself — that rule's
canonical home is src/atdd/planner/conventions/wmbt.convention.yaml, and the
rule-registration assertion lives in src/atdd/planner/validators/
test_wmbt_smoke_acceptance_rule_registered.py (#921).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.spawn_agents]

_TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent  # src/atdd/coach/
    / "templates"
    / "CONDUCTOR.md"
)

VALIDATE_CMD = "atdd validate planner --local --skip-api"


def _read_template() -> str:
    assert _TEMPLATE_PATH.exists(), f"Template not found: {_TEMPLATE_PATH}"
    return _TEMPLATE_PATH.read_text()


def _init_phase_section(content: str) -> str:
    """Return the text of the INIT phase block in atdd_cycle.phases.

    Extracts from '- name: INIT' to the next '- name:' entry so we can
    assert the gate is in the INIT phase context, not just anywhere in the file.
    """
    lines = content.splitlines()
    in_section = False
    out: list[str] = []
    for line in lines:
        if "- name: INIT" in line:
            in_section = True
        elif in_section and "- name:" in line:
            break
        if in_section:
            out.append(line)
    return "\n".join(out)


def test_atdd_md_init_phase_includes_validate_planner_command() -> None:
    """The INIT phase section of CONDUCTOR.md contains 'atdd validate planner --local --skip-api'."""
    content = _read_template()
    init_section = _init_phase_section(content)
    assert VALIDATE_CMD in init_section, (
        f"INIT phase section of CONDUCTOR.md does not contain the validator command '{VALIDATE_CMD}'. "
        "The pre_commit_gate in the INIT phase must include this command with --local --skip-api. "
        f"INIT phase section found:\n{init_section!r}"
    )


def test_atdd_md_init_phase_has_before_committing_timing_annotation() -> None:
    """The INIT phase section of CONDUCTOR.md contains 'before committing PLANNED' annotation."""
    content = _read_template()
    init_section = _init_phase_section(content).lower()
    assert "before committing" in init_section, (
        "INIT phase section of CONDUCTOR.md does not contain a 'before committing' timing annotation. "
        "The pre_commit_gate must specify the validator runs BEFORE committing PLANNED, "
        "not just before transitioning to RED."
    )
