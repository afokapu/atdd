# URN: acc:review-phase-boundaries:D001-UNIT-001-reviewer-cannot-write-worktree
# WMBT: plan/review_phase_boundaries/D001.yaml
# Harness: unit / backend

"""AC-UNIT-001: Reviewer agent spawned with ``--persona reviewer`` cannot run
``git commit`` or write to the worktree because the spawn adapter strips
commit/edit tools and embeds a no-write system prompt.

The reviewer's only output channel is
``atdd agent review --target-commit <sha> --report-file <path>``.
"""

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.platform]

SAMPLE_ISSUE_BODY = textwrap.dedent("""\
    ## Issue Metadata

    | Field | Value |
    |-------|-------|
    | Date | `2026-05-10` |
    | Status | `RED` |
    | Type | `implementation` |
    | Branch | `feat/review-test` |
    | Archetypes | `coach` |
    | Train | `0002-coach-drives-lifecycle` |
    | Wagon | `review-phase-boundaries` |
""")


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


class FakeMultiplexer:
    """Minimal multiplexer stub that satisfies cmd_spawn."""

    name = "fake"

    def new_surface(self, *, cwd, command, name=None):
        return "surface:reviewer-1"

    def new_workspace(self, *, cwd, command, name=None):
        return "workspace:reviewer-1"


@pytest.fixture()
def worktree(tmp_path: Path) -> Path:
    wt = tmp_path / "worktree"
    wt.mkdir()
    return wt


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    return tmp_path / ".atdd" / "runtime"


@pytest.fixture()
def fake_mpx():
    return FakeMultiplexer()


# ---------------------------------------------------------------------------
# Denied-tool set — every worktree-mutating surface the reviewer must not use
# ---------------------------------------------------------------------------

DENIED_TOOLS = frozenset({
    "Edit", "Write", "NotebookEdit", "MultiEdit",
    "Bash(git commit", "Bash(git push", "Bash(git reset",
    "Bash(dangerouslyDisableSandbox",
})


# ---------------------------------------------------------------------------
# Test 1: rendered launch prompt contains no-write system prompt
# ---------------------------------------------------------------------------


def test_reviewer_launch_prompt_contains_no_write_system_prompt(
    worktree: Path, runtime_root: Path, fake_mpx, monkeypatch,
):
    """When persona=reviewer, the launch prompt embeds a no-write system
    prompt that explicitly forbids edits."""
    from atdd.coach.commands import spawn

    monkeypatch.setattr(
        "atdd.coach.commands.session_template.fetch_issue",
        lambda n: {"number": n, "title": "Test issue", "body": SAMPLE_ISSUE_BODY},
    )

    spawn.cmd_spawn(
        persona="reviewer",
        llm="claude-code",
        worktree=worktree,
        issue=526,
        agent_id="reviewer-526-001",
        runtime_root=runtime_root,
        target_commit="abcd1234",
        multiplexer=fake_mpx,
    )

    prompt = (worktree / ".launch_prompt.txt").read_text()
    # The no-write system prompt must be present
    assert "reviewer" in prompt.lower()
    assert "no-write" in prompt.lower() or "no write" in prompt.lower()
    assert "edit" in prompt.lower()
    assert "commit" in prompt.lower()
    assert "forbidden" in prompt.lower() or "forbid" in prompt.lower() or "must not" in prompt.lower()


# ---------------------------------------------------------------------------
# Test 2: rendered prompt names atdd agent review as sole output channel
# ---------------------------------------------------------------------------


def test_reviewer_launch_prompt_names_review_as_sole_output_channel(
    worktree: Path, runtime_root: Path, fake_mpx, monkeypatch,
):
    """The reviewer launch prompt must name ``atdd agent review
    --target-commit <sha> --report-file <path>`` as the sole output channel."""
    from atdd.coach.commands import spawn

    monkeypatch.setattr(
        "atdd.coach.commands.session_template.fetch_issue",
        lambda n: {"number": n, "title": "Test issue", "body": SAMPLE_ISSUE_BODY},
    )

    spawn.cmd_spawn(
        persona="reviewer",
        llm="claude-code",
        worktree=worktree,
        issue=526,
        agent_id="reviewer-526-001",
        runtime_root=runtime_root,
        target_commit="abcd1234",
        multiplexer=fake_mpx,
    )

    prompt = (worktree / ".launch_prompt.txt").read_text()
    assert "atdd agent review" in prompt
    assert "--target-commit" in prompt
    assert "--report-file" in prompt


# ---------------------------------------------------------------------------
# Test 3: tool allowlist excludes every denied tool
# ---------------------------------------------------------------------------


def test_reviewer_tool_allowlist_excludes_write_tools(
    worktree: Path, runtime_root: Path, fake_mpx, monkeypatch,
):
    """The rendered tool allowlist must exclude Edit, Write, NotebookEdit,
    MultiEdit, git-commit, and other worktree-mutating surfaces."""
    from atdd.coach.commands import spawn

    monkeypatch.setattr(
        "atdd.coach.commands.session_template.fetch_issue",
        lambda n: {"number": n, "title": "Test issue", "body": SAMPLE_ISSUE_BODY},
    )

    spawn.cmd_spawn(
        persona="reviewer",
        llm="claude-code",
        worktree=worktree,
        issue=526,
        agent_id="reviewer-526-001",
        runtime_root=runtime_root,
        target_commit="abcd1234",
        multiplexer=fake_mpx,
    )

    prompt = (worktree / ".launch_prompt.txt").read_text()

    # The prompt must contain a tool-allowlist section
    assert "allowlist" in prompt.lower() or "allowed tools" in prompt.lower()

    # Extract the allowed-tools bullet block and check that denied tools
    # are NOT listed there. We match the "You may ONLY use" section
    # which contains backtick-quoted tool names as bullet items.
    import re

    allowlist_match = re.search(
        r"You may ONLY use the following tools:\s*\n([\s\S]*?)\n\n",
        prompt,
    )
    assert allowlist_match, "Tool allowlist block not found in prompt"
    allowlist_text = allowlist_match.group(1)

    for tool in DENIED_TOOLS:
        assert tool not in allowlist_text, (
            f"Denied tool {tool!r} found in reviewer allowed-tools block"
        )


# ---------------------------------------------------------------------------
# Test 4: non-reviewer persona does NOT get the no-write prompt
# ---------------------------------------------------------------------------


def test_coder_persona_does_not_get_no_write_prompt(
    worktree: Path, runtime_root: Path, fake_mpx, monkeypatch,
):
    """A non-reviewer persona (coder) must NOT receive the reviewer no-write
    system prompt or tool restrictions."""
    from atdd.coach.commands import spawn

    monkeypatch.setattr(
        "atdd.coach.commands.session_template.fetch_issue",
        lambda n: {"number": n, "title": "Test issue", "body": SAMPLE_ISSUE_BODY},
    )

    spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=526,
        agent_id="coder-526-001",
        runtime_root=runtime_root,
        multiplexer=fake_mpx,
    )

    prompt = (worktree / ".launch_prompt.txt").read_text()
    # The coder prompt should NOT contain the reviewer no-write section
    assert "no-write" not in prompt.lower()
    assert "denied tools" not in prompt.lower()


# ---------------------------------------------------------------------------
# Test 5: manifest.json records persona=reviewer at spawn time
# ---------------------------------------------------------------------------


def test_spawn_writes_manifest_with_reviewer_persona(
    worktree: Path, runtime_root: Path, fake_mpx, monkeypatch,
):
    """When persona=reviewer, cmd_spawn writes manifest.json with the
    persona field so downstream guards can read it."""
    from atdd.coach.commands import spawn

    monkeypatch.setattr(
        "atdd.coach.commands.session_template.fetch_issue",
        lambda n: {"number": n, "title": "Test issue", "body": SAMPLE_ISSUE_BODY},
    )

    spawn.cmd_spawn(
        persona="reviewer",
        llm="claude-code",
        worktree=worktree,
        issue=526,
        agent_id="reviewer-526-001",
        runtime_root=runtime_root,
        target_commit="abcd1234",
        multiplexer=fake_mpx,
    )

    manifest_path = runtime_root / "agents" / "reviewer-526-001" / "manifest.json"
    assert manifest_path.is_file(), "manifest.json must be written at spawn time"

    manifest = json.loads(manifest_path.read_text())
    assert manifest["persona"] == "reviewer"
