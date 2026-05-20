# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E006-UNIT-002-close-not-called-on-success
# Acceptance: acc:dispatch-ux-defaults-and-primer:E006-UNIT-002-close-not-called-on-success
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E006
# Phase: RED
# Layer: application
# Runtime: python
"""E006-UNIT-002 — backend.close is NOT called when the spawn pipeline completes successfully.

RED: The try/finally guard that would call backend.close doesn't wrap the
full post-creation pipeline yet. This test ensures the fix doesn't over-close:
on a successful spawn, no close should occur.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMultiplexer:
    def __init__(self):
        self.close_calls: list[str] = []

    def new_surface(self, *, cwd, command, name):
        return "surface:99"

    def close(self, surface_ref: str) -> None:
        self.close_calls.append(surface_ref)

    def rename(self, *args, **kwargs):
        pass

    def paste_text(self, *args, **kwargs):
        pass

    def send_key(self, *args, **kwargs):
        pass

    def capture_pane_text(self, *args, **kwargs):
        return ""


def test_close_not_called_on_successful_spawn(tmp_path):
    """backend.close is NOT called when cmd_spawn completes without error."""
    from atdd.coach.commands.spawn import cmd_spawn, PERSONAS, ADAPTER_REGISTRY

    fake_backend = _FakeMultiplexer()
    worktree = tmp_path / "feat-issue-999"
    worktree.mkdir()
    (worktree / ".git").mkdir()
    (worktree / "prompt.txt").write_text("prompt")

    persona = next(iter(PERSONAS))
    llm = next(iter(ADAPTER_REGISTRY))

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=worktree / "prompt.txt"),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._wait_for_claude_ready"),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn._assert_no_forbidden_flags"),
        patch("atdd.coach.commands.spawn._inject_agent_env", side_effect=lambda cmd, _: cmd),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD999"),
        patch("atdd.coach.commands.spawn._emit_agent_spawned_event"),
        patch("atdd.coach.commands.spawn._spawn_observer_if_configured"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
    ):
        result = cmd_spawn(
            persona=persona,
            llm=llm,
            worktree=worktree,
            issue=999,
            agent_id="tester-test-999",
            runtime_root=worktree,
            multiplexer=fake_backend,
        )

    assert fake_backend.close_calls == [], (
        f"backend.close must NOT be called on successful spawn; "
        f"close_calls={fake_backend.close_calls!r}"
    )
    assert result is not None, "cmd_spawn must return a result dict on success"
