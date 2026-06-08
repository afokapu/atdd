# URN: test:observe-and-correct:e001-unit-001
# Acceptance: acc:observe-and-correct:E001-UNIT-001-scope-batch-approves
# WMBT: wmbt:observe-and-correct:E001
# Phase: GREEN
# Layer: assembly
# Runtime: python
# Purpose: `atdd observer aggregate-approve --scope 358,359` approves matching
#          prompts across the named issues' sessions in a single batch action.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.commands.observer import (
    AggregateApprovalResult,
    cmd_aggregate_approve,
)

pytestmark = [pytest.mark.platform]

_PROMPT_MARKER = "Do you want to proceed?\n❯ 1. Yes\n  2. No\n"


def _setup_agent(
    runtime_dir: Path,
    agent_id: str,
    *,
    issue: int | None = None,
    output_log: str = "",
) -> Path:
    """Create an agent dir with optional context.json and output.log."""
    agent_dir = runtime_dir / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    if issue is not None:
        ctx = {"issue": issue, "phase": "GREEN"}
        (agent_dir / "context.json").write_text(json.dumps(ctx))
    if output_log:
        (agent_dir / "output.log").write_text(output_log)
    return agent_dir


# ---------------------------------------------------------------------------
# AC-UNIT-001: scope batch-approves across named issues
# ---------------------------------------------------------------------------


class TestScopeBatchApproves:
    """atdd observer aggregate-approve --scope 358,359 approves matching
    prompts across the named issues' sessions in a single batch action."""

    def test_approves_safe_prompts_in_scoped_sessions(self, tmp_path: Path):
        """Two sessions (358, 359) each blocked on a safe git command prompt;
        aggregate-approve --scope 358,359 approves both."""
        runtime = tmp_path / "rt"
        _setup_agent(
            runtime,
            "agent-a",
            issue=358,
            output_log="Bash(git status --short)\n" + _PROMPT_MARKER,
        )
        _setup_agent(
            runtime,
            "agent-b",
            issue=359,
            output_log="Bash(pytest -xvs)\n" + _PROMPT_MARKER,
        )

        result = cmd_aggregate_approve(
            runtime_dir=runtime, scope="358,359",
        )

        assert isinstance(result, AggregateApprovalResult)
        assert result.approved == 2
        assert result.escalated == 0

    def test_scope_filters_out_unlisted_issues(self, tmp_path: Path):
        """Issue 360 is not in --scope 358,359; its prompt is left alone."""
        runtime = tmp_path / "rt"
        _setup_agent(
            runtime,
            "agent-a",
            issue=358,
            output_log="Bash(git status)\n" + _PROMPT_MARKER,
        )
        _setup_agent(
            runtime,
            "agent-b",
            issue=360,
            output_log="Bash(pytest)\n" + _PROMPT_MARKER,
        )

        result = cmd_aggregate_approve(
            runtime_dir=runtime, scope="358,359",
        )

        assert result.approved == 1
        assert result.escalated == 0

    def test_no_scope_approves_all(self, tmp_path: Path):
        """Without --scope, all agent sessions are included."""
        runtime = tmp_path / "rt"
        _setup_agent(
            runtime,
            "agent-a",
            issue=358,
            output_log="Bash(git status)\n" + _PROMPT_MARKER,
        )
        _setup_agent(
            runtime,
            "agent-b",
            issue=359,
            output_log="Bash(ls -la)\n" + _PROMPT_MARKER,
        )

        result = cmd_aggregate_approve(runtime_dir=runtime)

        assert result.approved == 2

    def test_escalated_unknown_command_not_approved(self, tmp_path: Path):
        """An unknown Bash command is escalated, not approved."""
        runtime = tmp_path / "rt"
        _setup_agent(
            runtime,
            "agent-a",
            issue=358,
            output_log="Bash(curl https://example.com)\n" + _PROMPT_MARKER,
        )

        result = cmd_aggregate_approve(
            runtime_dir=runtime, scope="358",
        )

        assert result.approved == 0
        assert result.escalated == 1

    def test_violation_not_approved(self, tmp_path: Path):
        """A .atdd/ hand-edit is a violation, never auto-approved."""
        runtime = tmp_path / "rt"
        _setup_agent(
            runtime,
            "agent-a",
            issue=358,
            output_log="Edit(.atdd/manifest.yaml)\n" + _PROMPT_MARKER,
        )

        result = cmd_aggregate_approve(
            runtime_dir=runtime, scope="358",
        )

        assert result.approved == 0
        assert result.escalated == 1

    def test_idle_surface_skipped(self, tmp_path: Path):
        """An agent with no pending prompt is a no-op."""
        runtime = tmp_path / "rt"
        _setup_agent(
            runtime,
            "agent-a",
            issue=358,
            output_log="just some output, nothing pending\n",
        )

        result = cmd_aggregate_approve(
            runtime_dir=runtime, scope="358",
        )

        assert result.approved == 0
        assert result.escalated == 0

    def test_returns_per_surface_disposition(self, tmp_path: Path):
        """AggregateApprovalResult carries approvals_by_ref and
        escalations_by_ref for per-surface inspection."""
        runtime = tmp_path / "rt"
        _setup_agent(
            runtime,
            "agent-a",
            issue=358,
            output_log="Bash(git status)\n" + _PROMPT_MARKER,
        )
        _setup_agent(
            runtime,
            "agent-b",
            issue=359,
            output_log="Bash(curl https://x)\n" + _PROMPT_MARKER,
        )

        result = cmd_aggregate_approve(
            runtime_dir=runtime, scope="358,359",
        )

        assert result.approved == 1
        assert result.escalated == 1
        assert "agent-a" in result.approvals_by_ref
        assert "agent-b" in result.escalations_by_ref

    def test_bash_patterns_read_from_observer_convention(
        self, tmp_path: Path,
    ):
        """The observer's aggregate-approve uses the same bash classifier
        patterns as rule 13, from observer.convention.yaml (#513)."""
        runtime = tmp_path / "rt"
        # git status is in the allow list; curl is in the deny list
        _setup_agent(
            runtime,
            "agent-a",
            issue=358,
            output_log="Bash(git status)\n" + _PROMPT_MARKER,
        )
        _setup_agent(
            runtime,
            "agent-b",
            issue=359,
            output_log="Bash(curl https://evil.com)\n" + _PROMPT_MARKER,
        )

        result = cmd_aggregate_approve(
            runtime_dir=runtime, scope="358,359",
        )

        assert result.approved == 1  # git status approved
        assert result.escalated == 1  # curl escalated

    def test_writes_approval_signal_to_agent_dir(self, tmp_path: Path):
        """Approved prompts write a record to cli-return.jsonl in the
        agent's runtime dir."""
        runtime = tmp_path / "rt"
        _setup_agent(
            runtime,
            "agent-a",
            issue=358,
            output_log="Bash(git status)\n" + _PROMPT_MARKER,
        )

        cmd_aggregate_approve(runtime_dir=runtime, scope="358")

        approval_path = runtime / "agents" / "agent-a" / "cli-return.jsonl"
        assert approval_path.exists()
        lines = approval_path.read_text().splitlines()
        assert len(lines) >= 1
        rec = json.loads(lines[-1])
        assert rec.get("action") == "auto_approve"

    def test_empty_runtime_is_noop(self, tmp_path: Path):
        """No agent dirs → approved=0, escalated=0."""
        runtime = tmp_path / "rt"
        result = cmd_aggregate_approve(runtime_dir=runtime)
        assert result.approved == 0
        assert result.escalated == 0

    def test_agent_without_context_json_included_when_no_scope(
        self, tmp_path: Path,
    ):
        """Agent dirs without context.json are included when --scope is
        absent (they have no issue filter to fail)."""
        runtime = tmp_path / "rt"
        _setup_agent(
            runtime,
            "agent-orphan",
            output_log="Bash(git status)\n" + _PROMPT_MARKER,
        )

        result = cmd_aggregate_approve(runtime_dir=runtime)

        assert result.approved == 1

    def test_agent_without_context_json_excluded_by_scope(
        self, tmp_path: Path,
    ):
        """Agent dirs without context.json are excluded when --scope is set
        (we can't map them to an issue)."""
        runtime = tmp_path / "rt"
        _setup_agent(
            runtime,
            "agent-orphan",
            output_log="Bash(git status)\n" + _PROMPT_MARKER,
        )

        result = cmd_aggregate_approve(
            runtime_dir=runtime, scope="358",
        )

        assert result.approved == 0
