# URN: test:observe-and-correct:persona-shim-spawn-dispatch-wiring-gaps:E004-UNIT-002-inbox-priming-before-shim-starts
# Acceptance: acc:observe-and-correct:E004-UNIT-002-inbox-priming-before-shim-starts
# WMBT: wmbt:observe-and-correct:E004
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E004-UNIT-002 — cmd_spawn writes the launch prompt as the first cli-return.jsonl
entry BEFORE the surface is created; no paste_text is called when
ATDD_CORRECTION_TRANSPORT=cli-return.

RED: cmd_spawn currently performs no inbox priming. The cli-return.jsonl entry is
never written before (or after) spawn, and paste_text IS called via
_wait_for_claude_ready. These tests pin the desired behavior.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]


class _OrderedFakeMultiplexer:
    """Records the sequence of new_surface_in_pane and paste_text calls so tests
    can assert ordering (cli-return.jsonl written BEFORE surface creation)."""

    name = "fake"
    _counter = 0

    def __init__(self, agent_runtime_dir: Path) -> None:
        self._agent_dir = agent_runtime_dir
        self.call_log: list[str] = []  # "new_surface" | "paste_text"
        self.cli_return_snapshot_at_surface: list[dict] = []

    def resolve_focused_pane(self, workspace: Any = None) -> str:
        return "pane:1"

    def _record_surface(self, command: Any) -> str:
        self.call_log.append("new_surface")
        cli_return = self._agent_dir / "cli-return.jsonl"
        if cli_return.exists():
            entries = [json.loads(ln) for ln in cli_return.read_text().splitlines() if ln.strip()]
            self.cli_return_snapshot_at_surface.extend(entries)
        _OrderedFakeMultiplexer._counter += 1
        return f"surface:{_OrderedFakeMultiplexer._counter}"

    def new_surface_in_pane(
        self,
        pane_ref: Any = None,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        workspace: Any = None,
    ) -> str:
        return self._record_surface(command)

    def new_surface(
        self,
        *,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        workspace_ref: Any = None,
        pane_ref: Any = None,
        direction: Any = None,
    ) -> str:
        return self._record_surface(command)

    def rename(self, ref: str, name: str) -> None:
        pass

    def paste_text(self, ref: str, text: str) -> None:
        self.call_log.append("paste_text")

    def send_key(self, *args: Any, **kwargs: Any) -> None:
        pass

    def capture_pane_text(self, *args: Any, **kwargs: Any) -> str:
        return ""


_SAMPLE_BODY = """\
## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/wire-persona-shim-into-spawn-dispatch` |
| Train | `0002-coach-drives-lifecycle` |
"""

_PROMPT_TEXT = "launch prompt for issue 841"


def test_cli_return_priming_entry_written_before_surface_creation(tmp_path, monkeypatch):
    """cli-return.jsonl must contain the launch prompt entry at the moment
    new_surface is called — inbox priming precedes pane spawn.

    RED: no priming entry is written today.
    """
    from atdd.coach.commands import spawn, session_template

    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")
    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": _SAMPLE_BODY},
    )

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"
    agent_id = "coder-841-prm"
    agent_dir = runtime / "agents" / agent_id
    prompt_file = worktree / "prompt.txt"
    prompt_file.write_text(_PROMPT_TEXT)

    fake_mx = _OrderedFakeMultiplexer(agent_dir)

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=prompt_file),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._wait_for_claude_ready"),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD841"),
        patch("atdd.coach.commands.spawn._emit_agent_spawned_event"),
        patch("atdd.coach.commands.spawn._spawn_observer_if_configured"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
    ):
        spawn.cmd_spawn(
            persona="coder",
            llm="claude-code",
            worktree=worktree,
            issue=841,
            agent_id=agent_id,
            runtime_root=runtime,
            multiplexer=fake_mx,
        )

    # RED assertion 1: at least one entry was captured in cli-return.jsonl
    # at the moment new_surface was called (inbox primed before spawn).
    assert fake_mx.cli_return_snapshot_at_surface, (
        "cli-return.jsonl must contain the launch prompt entry BEFORE new_surface "
        "is called. No entries were present when new_surface fired."
    )

    # RED assertion 2: the entry's correction_text is the launch prompt.
    first_entry = fake_mx.cli_return_snapshot_at_surface[0]
    assert "correction_text" in first_entry, (
        f"cli-return.jsonl entry must have a 'correction_text' field. Got: {first_entry!r}"
    )
    assert _PROMPT_TEXT in first_entry["correction_text"], (
        f"correction_text must contain the launch prompt. "
        f"Got: {first_entry['correction_text']!r}"
    )


def test_paste_text_not_called_when_cli_return_transport(tmp_path, monkeypatch):
    """When ATDD_CORRECTION_TRANSPORT=cli-return, paste_text must NOT be called.
    The shim delivers the prompt via cli-return.jsonl instead.

    RED: paste_text IS called today via _wait_for_claude_ready.
    """
    from atdd.coach.commands import spawn, session_template

    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")
    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": _SAMPLE_BODY},
    )

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"
    agent_id = "coder-841-nopaste"
    agent_dir = runtime / "agents" / agent_id
    prompt_file = worktree / "prompt.txt"
    prompt_file.write_text(_PROMPT_TEXT)

    fake_mx = _OrderedFakeMultiplexer(agent_dir)

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=prompt_file),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._wait_for_claude_ready"),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD841"),
        patch("atdd.coach.commands.spawn._emit_agent_spawned_event"),
        patch("atdd.coach.commands.spawn._spawn_observer_if_configured"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
    ):
        spawn.cmd_spawn(
            persona="coder",
            llm="claude-code",
            worktree=worktree,
            issue=841,
            agent_id=agent_id,
            runtime_root=runtime,
            multiplexer=fake_mx,
        )

    assert "paste_text" not in fake_mx.call_log, (
        "paste_text must NOT be called when ATDD_CORRECTION_TRANSPORT=cli-return. "
        "The shim delivers the launch prompt via cli-return.jsonl. "
        f"Observed call log: {fake_mx.call_log}"
    )


def test_cli_return_file_exists_after_spawn(tmp_path, monkeypatch):
    """The agent's cli-return.jsonl must exist after cmd_spawn when
    ATDD_CORRECTION_TRANSPORT=cli-return (confirms priming file was written).

    RED: no cli-return.jsonl is written today.
    """
    from atdd.coach.commands import spawn, session_template

    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")
    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": _SAMPLE_BODY},
    )

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"
    agent_id = "coder-841-filecheck"
    agent_dir = runtime / "agents" / agent_id
    prompt_file = worktree / "prompt.txt"
    prompt_file.write_text(_PROMPT_TEXT)

    fake_mx = _OrderedFakeMultiplexer(agent_dir)

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=prompt_file),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._wait_for_claude_ready"),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD841"),
        patch("atdd.coach.commands.spawn._emit_agent_spawned_event"),
        patch("atdd.coach.commands.spawn._spawn_observer_if_configured"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
    ):
        spawn.cmd_spawn(
            persona="coder",
            llm="claude-code",
            worktree=worktree,
            issue=841,
            agent_id=agent_id,
            runtime_root=runtime,
            multiplexer=fake_mx,
        )

    cli_return_path = agent_dir / "cli-return.jsonl"
    assert cli_return_path.exists(), (
        f"cli-return.jsonl must exist after cmd_spawn with ATDD_CORRECTION_TRANSPORT=cli-return. "
        f"Expected: {cli_return_path}"
    )
    entries = [json.loads(ln) for ln in cli_return_path.read_text().splitlines() if ln.strip()]
    assert len(entries) == 1, (
        f"Exactly one inbox-priming entry must be written before the shim starts. "
        f"Got {len(entries)} entries."
    )
    assert entries[0].get("correction_text") == _PROMPT_TEXT, (
        f"The priming entry's correction_text must equal the launch prompt. "
        f"Got: {entries[0]!r}"
    )
