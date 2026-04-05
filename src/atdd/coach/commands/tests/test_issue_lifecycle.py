"""
Regression tests for issue lifecycle behavior.

Covers:
- Next-step guidance: canonical ATDD transition sequence GREEN -> SMOKE -> REFACTOR
- E013: Hard handoff enforcement for worktree discipline

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/commands/tests/test_issue_lifecycle.py -v
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.commands.issue_lifecycle import IssueLifecycle

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Helpers for next-step guidance tests (#174)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers for E013 hard handoff tests (#175)
# ---------------------------------------------------------------------------

def _make_issue(number=175, status="PLANNED", title="chore(atdd): Test Issue",
                branch="chore/test-issue", state="OPEN"):
    """Build a minimal issue dict matching gh CLI JSON output."""
    return {
        "number": number,
        "title": title,
        "state": state,
        "labels": [{"name": f"atdd:{status}"}],
        "body": (
            f"| Field | Value |\n"
            f"|-------|-------|\n"
            f"| Branch | <!-- fmt: {branch} -->`{branch}` |\n"
        ),
    }


def _make_lifecycle(target_dir_name="main"):
    """Create IssueLifecycle with a mocked target_dir."""
    mock_dir = MagicMock(spec=Path)
    mock_dir.name = target_dir_name
    mock_dir.parent = MagicMock(spec=Path)
    mock_dir.__truediv__ = lambda self, other: Path(f"/fake/{target_dir_name}/{other}")

    lifecycle = IssueLifecycle.__new__(IssueLifecycle)
    lifecycle.target_dir = mock_dir
    lifecycle.atdd_config_dir = mock_dir / ".atdd"
    lifecycle.config_file = mock_dir / ".atdd" / "config.yaml"
    return lifecycle


class TestEnterFromMain:
    """E013: enter() from main prints hard handoff without gate or full context."""

    def test_enter_planned_from_main_prints_handoff(self, capsys):
        """
        SPEC-LIFECYCLE-VAL-0010: PLANNED+ entry from main stops with cd handoff.

        Given: Issue #175 at PLANNED status
        When: enter() is called from the main worktree directory
        Then: Output contains cd handoff, does NOT contain full context banner
        """
        lifecycle = _make_lifecycle("main")
        issue = _make_issue(status="PLANNED")
        worktree_path = Path("/fake/chore-test-issue")

        with patch.object(lifecycle, "_fetch_issue", return_value=issue), \
             patch.object(lifecycle, "_fetch_sub_issues", return_value=[]), \
             patch.object(lifecycle, "_is_in_worktree", return_value=False), \
             patch.object(lifecycle, "_find_worktree_for_issue", return_value=worktree_path), \
             patch.object(lifecycle, "_run_gate") as mock_gate, \
             patch.object(lifecycle, "_print_context") as mock_context:

            rc = lifecycle.enter(175)

        assert rc == 0
        output = capsys.readouterr().out

        # Hard handoff printed
        assert "cd" in output, "Handoff must include cd command"
        assert "atdd issue 175" in output, "Handoff must include re-entry command"

        # Gate and full context NOT called
        mock_gate.assert_not_called()
        mock_context.assert_not_called()

    def test_enter_red_from_main_prints_handoff(self, capsys):
        """
        SPEC-LIFECYCLE-VAL-0010b: RED entry from main also triggers hard handoff.

        Given: Issue #175 at RED status
        When: enter() is called from main
        Then: Hard handoff, no gate or context
        """
        lifecycle = _make_lifecycle("main")
        issue = _make_issue(status="RED")
        worktree_path = Path("/fake/chore-test-issue")

        with patch.object(lifecycle, "_fetch_issue", return_value=issue), \
             patch.object(lifecycle, "_fetch_sub_issues", return_value=[]), \
             patch.object(lifecycle, "_is_in_worktree", return_value=False), \
             patch.object(lifecycle, "_find_worktree_for_issue", return_value=worktree_path), \
             patch.object(lifecycle, "_run_gate") as mock_gate, \
             patch.object(lifecycle, "_print_context") as mock_context:

            rc = lifecycle.enter(175)

        assert rc == 0
        mock_gate.assert_not_called()
        mock_context.assert_not_called()

    def test_enter_from_main_creates_worktree_if_missing(self, capsys):
        """
        SPEC-LIFECYCLE-VAL-0010c: enter() from main creates worktree when none exists.

        Given: Issue #175 at PLANNED, no worktree exists
        When: enter() is called from main
        Then: _create_branch is called, then hard handoff
        """
        lifecycle = _make_lifecycle("main")
        issue = _make_issue(status="PLANNED")
        worktree_path = Path("/fake/chore-test-issue")

        with patch.object(lifecycle, "_fetch_issue", return_value=issue), \
             patch.object(lifecycle, "_fetch_sub_issues", return_value=[]), \
             patch.object(lifecycle, "_is_in_worktree", return_value=False), \
             patch.object(lifecycle, "_find_worktree_for_issue", return_value=None), \
             patch.object(lifecycle, "_create_branch", return_value=worktree_path) as mock_create, \
             patch.object(lifecycle, "_run_gate") as mock_gate:

            rc = lifecycle.enter(175)

        assert rc == 0
        mock_create.assert_called_once_with(175, "test-issue", "chore")
        mock_gate.assert_not_called()


class TestEnterFromWorktree:
    """E013: enter() from correct worktree runs gate and prints context."""

    def test_enter_planned_from_worktree_runs_gate(self, capsys):
        """
        SPEC-LIFECYCLE-VAL-0011: PLANNED+ entry from worktree runs gate and shows context.

        Given: Issue #175 at PLANNED status
        When: enter() is called from the correct worktree directory
        Then: Gate runs and full context is printed
        """
        lifecycle = _make_lifecycle("chore-test-issue")
        issue = _make_issue(status="PLANNED")

        with patch.object(lifecycle, "_fetch_issue", return_value=issue), \
             patch.object(lifecycle, "_fetch_sub_issues", return_value=[]), \
             patch.object(lifecycle, "_is_in_worktree", return_value=True), \
             patch.object(lifecycle, "_run_gate") as mock_gate, \
             patch.object(lifecycle, "_print_context") as mock_context:

            rc = lifecycle.enter(175)

        assert rc == 0
        mock_gate.assert_called_once()
        mock_context.assert_called_once()


class TestEnterInitAndTerminal:
    """E013: enter() at INIT and terminal states behaves correctly."""

    def test_enter_init_no_branch(self, capsys):
        """
        SPEC-LIFECYCLE-VAL-0012: INIT entry prints context without branch or gate.

        Given: Issue #175 at INIT status
        When: enter() is called
        Then: Context is printed, no gate or branch creation
        """
        lifecycle = _make_lifecycle("main")
        issue = _make_issue(status="INIT")

        with patch.object(lifecycle, "_fetch_issue", return_value=issue), \
             patch.object(lifecycle, "_fetch_sub_issues", return_value=[]), \
             patch.object(lifecycle, "_run_gate") as mock_gate, \
             patch.object(lifecycle, "_print_context") as mock_context:

            rc = lifecycle.enter(175)

        assert rc == 0
        mock_gate.assert_not_called()
        mock_context.assert_called_once()

    def test_enter_complete_no_branch(self, capsys):
        """
        SPEC-LIFECYCLE-VAL-0013: COMPLETE entry prints context only.

        Given: Issue #175 at COMPLETE status
        When: enter() is called
        Then: Context is printed with terminal status, no gate
        """
        lifecycle = _make_lifecycle("main")
        issue = _make_issue(status="COMPLETE", state="CLOSED")

        with patch.object(lifecycle, "_fetch_issue", return_value=issue), \
             patch.object(lifecycle, "_fetch_sub_issues", return_value=[]), \
             patch.object(lifecycle, "_run_gate") as mock_gate, \
             patch.object(lifecycle, "_print_context") as mock_context:

            rc = lifecycle.enter(175)

        assert rc == 0
        mock_gate.assert_not_called()
        mock_context.assert_called_once()

    def test_enter_obsolete_no_branch(self, capsys):
        """
        SPEC-LIFECYCLE-VAL-0013b: OBSOLETE entry prints context only.

        Given: Issue #175 at OBSOLETE status
        When: enter() is called
        Then: Context is printed, no gate
        """
        lifecycle = _make_lifecycle("main")
        issue = _make_issue(status="OBSOLETE", state="CLOSED")

        with patch.object(lifecycle, "_fetch_issue", return_value=issue), \
             patch.object(lifecycle, "_fetch_sub_issues", return_value=[]), \
             patch.object(lifecycle, "_run_gate") as mock_gate, \
             patch.object(lifecycle, "_print_context") as mock_context:

            rc = lifecycle.enter(175)

        assert rc == 0
        mock_gate.assert_not_called()
        mock_context.assert_called_once()
