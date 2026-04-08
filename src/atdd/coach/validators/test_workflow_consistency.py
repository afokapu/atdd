"""
Workflow consistency checks for ATDD guidance documents.

Purpose:
  Keep the authoritative workflow docs aligned with the enforced
  state machine: GREEN -> SMOKE -> REFACTOR.

Run: atdd validate coach --local
"""

from pathlib import Path

import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root

REPO_ROOT = find_repo_root()
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
ISSUE_CONVENTION = ATDD_PKG_DIR / "coach" / "conventions" / "issue.convention.yaml"
ATDD_TEMPLATE = ATDD_PKG_DIR / "coach" / "templates" / "ATDD.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


def test_issue_convention_workflow_includes_smoke():
    """
    SPEC-COACH-WORKFLOW-0003: implementation workflow summary includes SMOKE.
    """
    with ISSUE_CONVENTION.open() as f:
        convention = yaml.safe_load(f) or {}

    workflow = convention["workflow"]["session_type_workflows"]["implementation"]["workflow"]
    assert workflow == "Full ATDD cycle: Plan \u2192 Test (RED) \u2192 Code (GREEN) \u2192 Test (SMOKE) \u2192 Refactor"


def test_atdd_template_after_coder_points_to_smoke():
    """
    SPEC-COACH-WORKFLOW-0004: ATDD template guidance points coder validation to SMOKE.
    """
    content = ATDD_TEMPLATE.read_text()
    assert 'after_coder: "atdd validate coder       # Before transitioning to SMOKE"' in content


def test_claude_after_coder_points_to_smoke():
    """
    SPEC-COACH-WORKFLOW-0005: CLAUDE guidance mirrors the SMOKE transition.
    """
    content = CLAUDE_MD.read_text()
    assert 'after_coder: "atdd validate coder       # Before transitioning to SMOKE"' in content
