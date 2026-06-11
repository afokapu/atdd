# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E006-UNIT-003-close-tolerates-close-failure
# Acceptance: acc:dispatch-ux-defaults-and-primer:E006-UNIT-003-close-tolerates-close-failure
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E006
# Phase: RED
# Layer: application
# Runtime: python
"""E006-UNIT-003 — when backend.close raises, the original spawn exception is still propagated.

RED: There is no try/finally guard around the full post-creation pipeline for
_wait_for_claude_ready, so backend.close is never called. Once the guard is
added (GREEN), it must not swallow the original error if close() itself raises.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMultiplexerCloseRaises:
    def __init__(self):
        self.new_surface_called = False
        self.close_calls: list[str] = []

    def new_surface(self, *, cwd, command, name):
        self.new_surface_called = True
        return "surface:99"

    def close(self, surface_ref: str) -> None:
        self.close_calls.append(surface_ref)
        raise RuntimeError("close failed")

    def rename(self, *args, **kwargs):
        pass

    def paste_text(self, *args, **kwargs):
        pass

    def send_key(self, *args, **kwargs):
        pass

    def capture_pane_text(self, *args, **kwargs):
        return ""


def test_original_exception_propagates_when_close_also_raises(tmp_path):
    """When both the pipeline and backend.close raise, WorkerReadinessTimeout propagates."""
    from atdd.coach.commands.spawn import cmd_spawn, WorkerReadinessTimeout, PERSONAS, ADAPTER_REGISTRY

    fake_backend = _FakeMultiplexerCloseRaises()
    worktree = tmp_path / "feat-issue-999"
    worktree.mkdir()
    (worktree / ".git").mkdir()
    (worktree / "prompt.txt").write_text("prompt")

    persona = next(iter(PERSONAS))
    llm = next(iter(ADAPTER_REGISTRY))

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=worktree / "prompt.txt"),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._wait_for_claude_ready",
              side_effect=WorkerReadinessTimeout("original-timeout")),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn._assert_no_forbidden_flags"),
        patch("atdd.coach.commands.spawn._inject_agent_env", side_effect=lambda cmd, _aid, **_kw: ({}, cmd)),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD999"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
    ):
        exc = None
        try:
            cmd_spawn(
                persona=persona,
                llm=llm,
                worktree=worktree,
                issue=999,
                agent_id="tester-test-999",
                runtime_root=worktree,
                multiplexer=fake_backend,
            )
        except Exception as e:
            exc = e

    assert exc is not None, "cmd_spawn must raise when WorkerReadinessTimeout occurs"

    is_original = isinstance(exc, WorkerReadinessTimeout) or (
        exc.__context__ is not None and isinstance(exc.__context__, WorkerReadinessTimeout)
    ) or (
        exc.__cause__ is not None and isinstance(exc.__cause__, WorkerReadinessTimeout)
    )
    assert is_original, (
        f"the original WorkerReadinessTimeout must be in the exception chain; "
        f"got {type(exc).__name__}: {exc!r}"
    )
