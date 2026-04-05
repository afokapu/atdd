"""
Regression tests for issue lifecycle next-step guidance.

Purpose:
  Ensure the lifecycle helper keeps the canonical ATDD transition
  sequence GREEN -> SMOKE -> REFACTOR.
"""

from pathlib import Path

from atdd.coach.commands.issue_lifecycle import IssueLifecycle


def _print_context_for_status(status: str, capsys) -> str:
    lifecycle = IssueLifecycle(target_dir=Path.cwd())
    issue = {"number": 174, "title": "Workflow consistency", "state": "OPEN"}

    lifecycle._print_context(
        issue=issue,
        status=status,
        sub_issues=[],
        slug="smoke-workflow-consistency",
        prefix="chore",
        worktree_path=None,
    )

    return capsys.readouterr().out


def test_green_status_points_to_smoke(capsys):
    """
    SPEC-COACH-WORKFLOW-0001: GREEN helper output points to SMOKE.
    """
    output = _print_context_for_status("GREEN", capsys)

    assert "Run tester SMOKE verification" in output
    assert "atdd issue 174 --status SMOKE" in output


def test_smoke_status_points_to_refactor(capsys):
    """
    SPEC-COACH-WORKFLOW-0002: SMOKE helper output points to REFACTOR.
    """
    output = _print_context_for_status("SMOKE", capsys)

    assert "Refactor to clean architecture" in output
    assert "atdd issue 174 --status REFACTOR" in output
