# URN: test:govern-lifecycle:cmux-native-worker-launcher:E043-UNIT-002-spawn-default-routes-cmux-native-killswitch-shim
# Acceptance: acc:govern-lifecycle:E043-UNIT-002-spawn-default-routes-cmux-native-killswitch-shim
# WMBT: wmbt:govern-lifecycle:E043
# Phase: GREEN
"""acc:govern-lifecycle:E043-UNIT-002 — the spawn DEFAULT launches the worker
cmux-native (agent positional prompt seeds the surface; NO shim wrap, NO
cli-return inbox, NO post-boot paste), and the ``ATDD_USE_LEGACY_SPAWN=1`` kill
switch still routes to the shim (cli-return) for the soak.

#978: cmux opens the surface running the agent and the positional prompt both
lands AND auto-submits the first turn (2026-06-05 spike). The shim is the proven
fallback kept until #979 deletes it.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]

_SEED = "SEED-978 do the tiny thing"


class _FakeMultiplexer:
    name = "fake"
    _counter = 0

    def __init__(self) -> None:
        self.surface_commands: list[str] = []
        self.paste_calls: list[str] = []

    def resolve_focused_pane(self, workspace: Any = None) -> str:
        return "pane:1"

    def new_surface_in_pane(self, pane_ref: Any = None, cwd: Any = None,
                            command: Any = None, name: Any = None,
                            workspace: Any = None) -> str:
        self.surface_commands.append(command or "")
        _FakeMultiplexer._counter += 1
        return f"surface:{_FakeMultiplexer._counter}"

    def surface_to_pane(self, surface_ref: Any, workspace: Any = None) -> str:
        return "pane:1"  # surface is live

    def rename(self, ref: str, name: str) -> None:
        pass

    def paste_text(self, ref: str, text: str) -> None:
        self.paste_calls.append(text)

    def send_key(self, *args: Any, **kwargs: Any) -> None:
        pass

    def capture_pane_text(self, *args: Any, **kwargs: Any) -> str:
        return ""


def _run_cmd_spawn(tmp_path, multiplexer, monkeypatch):
    from atdd.coach.commands import spawn, session_template

    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": ""},
    )
    worktree = tmp_path / "wt"
    worktree.mkdir(exist_ok=True)
    runtime = tmp_path / "rt"
    prompt_file = worktree / "prompt.txt"
    prompt_file.write_text(_SEED)

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=prompt_file),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD978"),
        patch("atdd.coach.commands.spawn._emit_agent_spawned_event"),
        patch("atdd.coach.commands.spawn._spawn_observer_if_configured"),
        patch("atdd.coach.commands.spawn.capture_session_uuid"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
        # Isolate the command-building / priming assertions from liveness +
        # the legacy paste readiness stages.
        patch("atdd.coach.commands.spawn._verify_process_alive"),
        patch("atdd.coach.commands.spawn._verify_cmux_surface_alive"),
        patch("atdd.coach.commands.spawn.SurfaceMarkerProbe.wait_for_ready"),
        patch("atdd.coach.commands.spawn._verify_stage"),
        patch("atdd.coach.commands.spawn._assert_worker_processing"),
    ):
        spawn.cmd_spawn(
            persona="coder",
            llm="claude-code",
            worktree=worktree,
            issue=978,
            agent_id="coder-978-002",
            runtime_root=runtime,
            multiplexer=multiplexer,
        )
    return runtime


def test_resolve_transport_default_is_cmux_native_killswitch_is_shim():
    from atdd.runtime.agent_control import resolve_transport

    assert resolve_transport({}) == "cmux-native"
    assert resolve_transport({"ATDD_USE_LEGACY_SPAWN": "1"}) == "cli-return"
    # An explicit override still wins (incl. the deprecated direct path).
    assert resolve_transport({"ATDD_CORRECTION_TRANSPORT": "tui-scrape"}) == "tui-scrape"


def test_default_spawn_seeds_positional_prompt_no_shim_no_inbox_no_paste(tmp_path, monkeypatch):
    """DEFAULT (no transport env) → cmux-native: the surface command carries the
    launch prompt as the positional seed before --allowedTools, is never shim
    wrapped, primes no cli-return inbox, and fires no paste_text."""
    monkeypatch.delenv("ATDD_CORRECTION_TRANSPORT", raising=False)
    monkeypatch.delenv("ATDD_USE_LEGACY_SPAWN", raising=False)
    fake_mx = _FakeMultiplexer()
    runtime = _run_cmd_spawn(tmp_path, fake_mx, monkeypatch)

    assert fake_mx.surface_commands, "a surface must be created"
    surface_cmd = fake_mx.surface_commands[-1]

    # No shim in the launch command.
    assert "atdd.coach.shim" not in surface_cmd, surface_cmd
    assert "atdd.runtime.agent_control" not in surface_cmd, surface_cmd
    assert not surface_cmd.lstrip().startswith("atdd-shim"), surface_cmd

    # The positional prompt seeds the first turn, BEFORE the variadic --allowedTools.
    parsed = shlex.split(surface_cmd)
    assert _SEED in parsed, f"positional seed missing from {surface_cmd!r}"
    assert "claude" in parsed
    # prompt is the token immediately after the agent binary
    assert parsed[parsed.index("claude") + 1] == _SEED
    assert parsed.index(_SEED) < parsed.index("--allowedTools")

    # No cli-return inbox primed.
    inbox = runtime / "agents" / "coder-978-002" / "cli-return.jsonl"
    if inbox.exists():
        rows = [ln for ln in inbox.read_text().splitlines() if ln.strip()]
        assert rows == [], f"cmux-native must not prime cli-return inbox: {rows!r}"

    # No post-boot paste fired.
    assert fake_mx.paste_calls == [], f"cmux-native must not paste: {fake_mx.paste_calls!r}"


def test_killswitch_routes_to_shim_and_primes_inbox(tmp_path, monkeypatch):
    """ATDD_USE_LEGACY_SPAWN=1 → the shim (cli-return): the surface command IS the
    shim wrapper and the cli-return inbox is primed with the launch prompt."""
    monkeypatch.delenv("ATDD_CORRECTION_TRANSPORT", raising=False)
    monkeypatch.setenv("ATDD_USE_LEGACY_SPAWN", "1")
    fake_mx = _FakeMultiplexer()
    runtime = _run_cmd_spawn(tmp_path, fake_mx, monkeypatch)

    surface_cmd = fake_mx.surface_commands[-1]
    assert "atdd.coach.shim" in surface_cmd, (
        f"ATDD_USE_LEGACY_SPAWN=1 must wrap the command in the shim. Got: {surface_cmd!r}"
    )

    inbox = runtime / "agents" / "coder-978-002" / "cli-return.jsonl"
    assert inbox.exists(), "the shim path must prime the cli-return inbox"
    rows = [json.loads(ln) for ln in inbox.read_text().splitlines() if ln.strip()]
    assert any(_SEED in (r.get("correction_text") or "") for r in rows), rows
    # The shim path delivers via the inbox, not a paste.
    assert fake_mx.paste_calls == []
