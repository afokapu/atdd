# URN: test:spawn-agents:atdd-spawn-skeleton-and-harness:E001-UNIT-002-claude-code-adapter-invoked
# Acceptance: acc:spawn-agents:E001-UNIT-002-claude-code-adapter-invoked
# WMBT: wmbt:spawn-agents:E001
# Phase: RED
# Layer: application
"""E001-UNIT-002 — `--llm claude-code` shells out to
``claude --dangerously-skip-permissions "$(cat <prompt>)"`` per spec §5.2,
and adapter selection is dispatched off ``--llm`` so other LLMs register
as separate adapters in K-track follow-ups without editing ``spawn.py``'s
CLI surface.

Issue #499.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/spawn-test` |
| Train | `0002-coach-drives-lifecycle` |
| Feature | adapter dispatch test |
"""


class FakeMultiplexer:
    """Captures the command string fed to new_surface so the test can
    assert against the exact claude-code invocation."""

    name = "fake"

    def __init__(self) -> None:
        self.last_command: Optional[str] = None
        self.last_cwd: Optional[str] = None
        self.pasted_text: Optional[str] = None
        self.keys_sent: list[str] = []

    def paste_text(self, ref: Any, text: str) -> None:
        self.pasted_text = text

    def send_key(self, ref: Any, key: str) -> None:
        self.keys_sent.append(key)

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        self.last_cwd = cwd
        self.last_command = command
        return "workspace:1"

    def new_surface(
        self,
        workspace_ref: Optional[str] = None,
        pane_ref: Optional[str] = None,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> str:
        self.last_cwd = cwd
        self.last_command = command
        return "surface:1"

    def new_persona_surface(
        self,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        *,
        observer_runtime_root: str = "",
        observer_agent_id: str = "",
        observer_name: str = "",
        observer_command: str = "",
        **_: Any,
    ) -> str:
        persona_ref = self.new_surface(cwd=cwd, command=command, name=name)
        # Preserve the persona command: observer surface creation must not
        # overwrite last_command (which is what tests assert against).
        saved_command = self.last_command
        saved_cwd = self.last_cwd
        try:
            self.new_surface(cwd=cwd, command=observer_command, name=observer_name)
        except Exception:
            pass
        self.last_command = saved_command
        self.last_cwd = saved_cwd
        return persona_ref


def test_adapter_registry_exposes_claude_code():
    """``claude-code`` MUST be a registered adapter; the registry is the
    open extension point that follow-up K-track issues add codex / gemini
    / glm to without editing ``spawn.py``'s CLI surface."""
    from atdd.coach.commands import spawn

    assert isinstance(spawn.ADAPTER_REGISTRY, dict)
    assert "claude-code" in spawn.ADAPTER_REGISTRY
    assert callable(spawn.ADAPTER_REGISTRY["claude-code"])


def test_claude_code_adapter_returns_bare_interactive_invocation(tmp_path):
    """The claude-code adapter MUST produce a BARE interactive invocation —
    no positional prompt arg. Claude Code v2.1.x ignores a positional
    prompt in interactive mode (#702); the prompt is injected post-boot by
    cmd_spawn via paste_text + send_key. The adapter must NOT embed
    `$(cat ...)` or the prompt path as an argv element."""
    from atdd.coach.commands import spawn

    prompt_path = tmp_path / ".launch_prompt.txt"
    prompt_path.write_text("body")
    cmd = spawn.ADAPTER_REGISTRY["claude-code"](prompt_path)
    assert cmd == (
        'claude --permission-mode acceptEdits '
        '--allowedTools "Read Edit Write TodoWrite Glob Grep WebFetch"'
    )
    # Regression guard (#702): no positional prompt / cat substitution.
    assert "$(cat" not in cmd
    assert str(prompt_path) not in cmd


def test_spawn_dispatches_adapter_off_llm_flag(tmp_path, monkeypatch):
    """``cmd_spawn(llm="claude-code", ...)`` MUST resolve and use the
    claude-code adapter — the multiplexer surface receives the adapter's
    command string."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"

    fake_mx = FakeMultiplexer()
    spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=358,
        agent_id="coder-358-001",
        runtime_root=runtime,
        multiplexer=fake_mx,
    )

    expected = (
        'claude --permission-mode acceptEdits '
        '--allowedTools "Read Edit Write TodoWrite Glob Grep WebFetch"'
    )
    assert fake_mx.last_command == expected

    # #702: the launch prompt is injected post-boot, not via argv. The
    # rendered .launch_prompt.txt content must be pasted, then submitted.
    prompt_file = worktree / ".launch_prompt.txt"
    assert fake_mx.pasted_text == prompt_file.read_text()
    assert "Enter" in fake_mx.keys_sent


def test_unknown_llm_rejected_with_clear_error(tmp_path, monkeypatch):
    """An ``--llm`` value that has no registered adapter MUST raise a
    clear error so the operator knows which adapters are wired."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )
    worktree = tmp_path / "wt"
    worktree.mkdir()

    with pytest.raises(ValueError) as exc:
        spawn.cmd_spawn(
            persona="coder",
            llm="not-a-real-llm",
            worktree=worktree,
            issue=358,
            agent_id="coder-358-001",
            runtime_root=tmp_path / "rt",
            multiplexer=FakeMultiplexer(),
        )
    msg = str(exc.value)
    assert "not-a-real-llm" in msg
    assert "claude-code" in msg  # Show the registered adapters.


def test_adapter_extension_point_does_not_require_editing_cli_surface():
    """A new LLM adapter MUST be registerable on ``ADAPTER_REGISTRY``
    without editing ``_build_parser()``'s CLI surface — the parser MUST
    accept arbitrary string values for ``--llm``, with adapter validation
    deferred to dispatch time."""
    from atdd.coach.commands import spawn

    parser = spawn._build_parser()
    # Arbitrary adapter name parses cleanly; it is rejected later only if
    # not registered. This is the contract that lets follow-up K-track
    # issues land codex / gemini / glm without touching spawn.py.
    parsed = parser.parse_args([
        "--persona", "coder",
        "--llm", "future-adapter-not-yet-shipped",
        "--worktree", "/tmp/wt",
        "--issue", "1",
        "--agent-id", "x",
        "--runtime", "/tmp/rt",
    ])
    assert parsed.llm == "future-adapter-not-yet-shipped"
