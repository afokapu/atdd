# URN: test:spawn-agents:E026-UNIT-003-render-launch-prompt-omits-graph-on-command-failure
# Acceptance: acc:spawn-agents:E026-UNIT-003-render-launch-prompt-omits-graph-on-command-failure
# WMBT: wmbt:spawn-agents:E026
# Phase: RED
# Layer: unit
"""E026-UNIT-003 — _render_launch_prompt gracefully omits the wagon-graph section
when `atdd repo graph --wagon <wagon> --format launch-prompt` fails (non-zero
exit or subprocess exception), rather than raising or blocking dispatch.

Setup:
  - _build_wagon_graph_section is patched to raise an exception (simulating
    subprocess failure or unknown wagon).

Assertions:
  1. No exception propagates from _render_launch_prompt.
  2. The returned prompt is a non-empty string.
  3. The returned prompt does NOT contain a Python traceback.

Phase RED: fails because `_build_wagon_graph_section` does not yet exist as
a callable in atdd.coach.commands.spawn — patch() raises AttributeError.
Phase GREEN: function exists and the exception is swallowed gracefully;
dispatch continues with a prompt that lacks the wagon-graph section.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.spawn_agents]


def test_no_exception_when_graph_command_fails(tmp_path: Path) -> None:
    """_render_launch_prompt must not raise when _build_wagon_graph_section raises."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands.session_template import IssueContext

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    with (
        patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"body": "Body.\n", "title": "Unknown wagon issue"},
        ),
        patch(
            "atdd.coach.commands.session_template.build_context",
            return_value=IssueContext(
                number=999,
                title="Unknown wagon issue",
                worktree_path=str(worktree),
            ),
        ),
        patch(
            "atdd.coach.commands.session_template.render",
            return_value="# Issue 999\n\nSome content.\n",
        ),
        patch("atdd.coach.commands.spawn._build_arch_section", return_value=None),
        patch(
            "atdd.coach.commands.spawn._build_wagon_graph_section",  # does not exist yet → RED
            side_effect=RuntimeError("subprocess exited 1: unknown wagon"),
        ),
    ):
        # Must NOT raise — graceful degrade required.
        try:
            prompt_path = spawn._render_launch_prompt(999, worktree)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(
                f"_render_launch_prompt raised {type(exc).__name__}: {exc}. "
                "Expected graceful degrade when _build_wagon_graph_section fails."
            )


def test_prompt_is_non_empty_when_graph_command_fails(tmp_path: Path) -> None:
    """The rendered prompt must be non-empty even when graph section is unavailable."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands.session_template import IssueContext

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    with (
        patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"body": "Body.\n", "title": "T"},
        ),
        patch(
            "atdd.coach.commands.session_template.build_context",
            return_value=IssueContext(number=999, title="T", worktree_path=str(worktree)),
        ),
        patch(
            "atdd.coach.commands.session_template.render",
            return_value="# Issue 999\n\nSome content.\n",
        ),
        patch("atdd.coach.commands.spawn._build_arch_section", return_value=None),
        patch(
            "atdd.coach.commands.spawn._build_wagon_graph_section",
            side_effect=RuntimeError("subprocess exited 1"),
        ),
    ):
        try:
            prompt_path = spawn._render_launch_prompt(999, worktree)
        except Exception:  # noqa: BLE001
            pytest.skip("_render_launch_prompt raised (tested in other test)")

    content = prompt_path.read_text()
    assert content.strip(), (
        "Expected non-empty prompt even when wagon-graph section is unavailable."
    )


def test_prompt_has_no_traceback_when_graph_command_fails(tmp_path: Path) -> None:
    """The rendered prompt must not contain a Python traceback on failure."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands.session_template import IssueContext

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    with (
        patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"body": "Body.\n", "title": "T"},
        ),
        patch(
            "atdd.coach.commands.session_template.build_context",
            return_value=IssueContext(number=999, title="T", worktree_path=str(worktree)),
        ),
        patch(
            "atdd.coach.commands.session_template.render",
            return_value="# Issue 999\n\nSome content.\n",
        ),
        patch("atdd.coach.commands.spawn._build_arch_section", return_value=None),
        patch(
            "atdd.coach.commands.spawn._build_wagon_graph_section",
            side_effect=RuntimeError("subprocess exited 1"),
        ),
    ):
        try:
            prompt_path = spawn._render_launch_prompt(999, worktree)
        except Exception:  # noqa: BLE001
            pytest.skip("_render_launch_prompt raised (tested in other test)")

    content = prompt_path.read_text()
    assert "Traceback (most recent call last)" not in content, (
        "Rendered prompt contains a Python traceback. "
        "E026: exceptions in _build_wagon_graph_section must be swallowed silently."
    )
