# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E006-UNIT-001-close-called-on-exception-after-surface-create
# Acceptance: acc:dispatch-ux-defaults-and-primer:E006-UNIT-001-close-called-on-exception-after-surface-create
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E006
# Phase: RED
# Layer: application
# Runtime: python
"""E006-UNIT-001 — backend.close is called when an exception occurs post surface-creation.

RED: The post-surface-creation pipeline (specifically _wait_for_claude_ready
and later stages) does not call backend.close on all exception paths. Only
the apply_canonical_name_and_layout step is wrapped in a try/finally guard.
A WorkerReadinessTimeout from _wait_for_claude_ready leaves an orphan pane.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMultiplexer:
    def __init__(self):
        self.close_calls: list[str] = []
        self.new_surface_called = False

    def new_surface(self, *, cwd, command, name):
        self.new_surface_called = True
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


def _minimal_cmd_spawn_kwargs(worktree: Path, backend) -> dict:
    from atdd.coach.commands.spawn import PERSONAS, ADAPTER_REGISTRY

    persona = next(iter(PERSONAS))
    llm = next(iter(ADAPTER_REGISTRY))
    return dict(
        persona=persona,
        llm=llm,
        worktree=worktree,
        issue=999,
        agent_id="tester-test-999",
        runtime_root=worktree,
        multiplexer=backend,
    )


def test_close_called_on_post_creation_exception(tmp_path):
    """backend.close is called with the surface_ref when _wait_for_claude_ready raises."""
    from atdd.coach.commands.spawn import cmd_spawn, WorkerReadinessTimeout

    fake_backend = _FakeMultiplexer()
    worktree = tmp_path / "feat-issue-999"
    worktree.mkdir()
    (worktree / ".git").mkdir()

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=worktree / "prompt.txt"),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._wait_for_claude_ready",
              side_effect=WorkerReadinessTimeout("timed out")),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn._assert_no_forbidden_flags"),
        patch("atdd.coach.commands.spawn._inject_agent_env", side_effect=lambda cmd, _aid, **_kw: ({}, cmd)),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD999"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
    ):
        (worktree / "prompt.txt").write_text("prompt")
        kwargs = _minimal_cmd_spawn_kwargs(worktree, fake_backend)

        with pytest.raises(WorkerReadinessTimeout):
            cmd_spawn(**kwargs)

    assert fake_backend.close_calls == ["surface:99"], (
        f"backend.close must be called with 'surface:99' on WorkerReadinessTimeout; "
        f"close_calls={fake_backend.close_calls!r}"
    )


def test_original_exception_propagates(tmp_path):
    """The original WorkerReadinessTimeout propagates from cmd_spawn (not swallowed)."""
    from atdd.coach.commands.spawn import cmd_spawn, WorkerReadinessTimeout

    fake_backend = _FakeMultiplexer()
    worktree = tmp_path / "feat-issue-999"
    worktree.mkdir()
    (worktree / ".git").mkdir()
    (worktree / "prompt.txt").write_text("prompt")

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=worktree / "prompt.txt"),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._wait_for_claude_ready",
              side_effect=WorkerReadinessTimeout("specific-timeout-message")),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn._assert_no_forbidden_flags"),
        patch("atdd.coach.commands.spawn._inject_agent_env", side_effect=lambda cmd, _aid, **_kw: ({}, cmd)),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD999"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
    ):
        kwargs = _minimal_cmd_spawn_kwargs(worktree, fake_backend)
        with pytest.raises(WorkerReadinessTimeout, match="specific-timeout-message"):
            cmd_spawn(**kwargs)
