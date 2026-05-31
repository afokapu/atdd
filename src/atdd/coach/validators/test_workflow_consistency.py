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
ATDD_TEMPLATE = ATDD_PKG_DIR / "coach" / "templates" / "CONDUCTOR.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


def test_issue_convention_workflow_includes_smoke():
    """
    SPEC-COACH-WORKFLOW-0003: implementation workflow summary includes SMOKE.
    """
    with ISSUE_CONVENTION.open() as f:
        convention = yaml.safe_load(f) or {}

    workflow = convention["workflow"]["session_type_workflows"]["implementation"]["workflow"]
    assert workflow == "Full ATDD cycle: Plan \u2192 Test (RED) \u2192 Code (GREEN) \u2192 Test (SMOKE) \u2192 Refactor"


# SPEC-COACH-WORKFLOW-0004 / 0005 (test_atdd_template_after_coder_points_to_smoke,
# test_claude_after_coder_points_to_smoke) removed in #919 Section B. Both asserted
# a hard-coded prose string from the `audits.workflow.after_coder` block in
# CONDUCTOR.md — the entire `audits:` block was deleted in Section B as forbidden
# duplication (canonical home: `atdd validate --help`). The operator-facing
# "validate coder before SMOKE" guidance now lives where it belongs (the CLI help
# surface); the template-prose assertions had nothing to assert against and no
# canonical home to migrate to.
