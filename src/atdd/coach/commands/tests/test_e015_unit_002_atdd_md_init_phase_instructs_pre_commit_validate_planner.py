# Acceptance: acc:spawn-agents:E015-UNIT-002-atdd-md-init-phase-instructs-pre-commit-validate-planner
"""
E015 AC-UNIT-002: ATDD.md template INIT phase block contains a pre_commit_gate
key naming planner.wmbt.must-have-smoke-acceptance and the validate command with
a 'BEFORE committing PLANNED' timing annotation.

ATDD.md is the persistent instruction file installed in every worktree via
atdd sync. Augmenting the INIT phase with an explicit pre_commit_gate ensures
any agent that reads the worktree CLAUDE.md sees the gate requirement, not just
agents reading the spawn-time SESSION-LAUNCH-TEMPLATE.md.

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
    / "ATDD.md"
)

RULE_ID = "planner.wmbt.must-have-smoke-acceptance"
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


def test_atdd_md_names_must_have_smoke_acceptance_rule() -> None:
    """ATDD.md contains the rule ID 'planner.wmbt.must-have-smoke-acceptance'."""
    content = _read_template()
    assert RULE_ID in content, (
        f"ATDD.md does not contain the rule ID '{RULE_ID}'. "
        "Add a pre_commit_gate key to the INIT phase block in the atdd_cycle.phases section."
    )


def test_atdd_md_init_phase_includes_validate_planner_command() -> None:
    """The INIT phase section of ATDD.md contains 'atdd validate planner --local --skip-api'."""
    content = _read_template()
    init_section = _init_phase_section(content)
    assert VALIDATE_CMD in init_section, (
        f"INIT phase section of ATDD.md does not contain the validator command '{VALIDATE_CMD}'. "
        "The pre_commit_gate in the INIT phase must include this command with --local --skip-api. "
        f"INIT phase section found:\n{init_section!r}"
    )


def test_atdd_md_init_phase_has_before_committing_timing_annotation() -> None:
    """The INIT phase section of ATDD.md contains 'before committing PLANNED' annotation."""
    content = _read_template()
    init_section = _init_phase_section(content).lower()
    assert "before committing" in init_section, (
        "INIT phase section of ATDD.md does not contain a 'before committing' timing annotation. "
        "The pre_commit_gate must specify the validator runs BEFORE committing PLANNED, "
        "not just before transitioning to RED."
    )
