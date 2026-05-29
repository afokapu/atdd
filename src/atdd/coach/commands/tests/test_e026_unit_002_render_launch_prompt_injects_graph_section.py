# URN: test:spawn-agents:E026-UNIT-002-render-launch-prompt-injects-graph-section
# Acceptance: acc:spawn-agents:E026-UNIT-002-render-launch-prompt-injects-graph-section
# WMBT: wmbt:spawn-agents:E026
# Phase: RED
# Layer: unit
"""E026-UNIT-002 — _render_launch_prompt injects the wagon-scoped graph output
between the issue body section and the persona instructions section of the
rendered prompt.

Setup:
  - session_template functions are monkeypatched to return fixture content.
  - _build_wagon_graph_section is patched to return a known fixture string.
  - _build_arch_section is patched to None (suppress legacy arch section).

Assertions:
  1. The fixture graph string appears in the rendered prompt.
  2. The fixture string appears AFTER the issue body section.
  3. The fixture string appears BEFORE the persona instructions section.
  4. The section is bounded by '## Wagon Architecture'.

Phase RED: fails because `_build_wagon_graph_section` does not yet exist as
a callable in atdd.coach.commands.spawn — `patch()` raises AttributeError.
Phase GREEN: function exists; all four assertions pass.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.spawn_agents]

_FIXTURE_GRAPH = (
    "## Wagon Architecture\n\n"
    "**Wagon:** `wagon:spawn-agents` — Spawn Agents\n"
    "> Fixture graph section for E026 unit test.\n\n"
    "**WMBTs:** E025, E026, E027\n\n"
)

_ISSUE_BODY_MARKER = "## Issue context"
_PERSONA_MARKER = "## Workflow"


def test_render_launch_prompt_contains_graph_section(tmp_path: Path) -> None:
    """The rendered prompt must contain the wagon-graph fixture string."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands.session_template import IssueContext

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    with (
        patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"body": "# Issue body\nSome content.\n", "title": "Wagon graph test"},
        ),
        patch(
            "atdd.coach.commands.session_template.build_context",
            return_value=IssueContext(
                number=864,
                title="Wagon graph test",
                worktree_path=str(worktree),
            ),
        ),
        patch(
            "atdd.coach.commands.session_template.render",
            return_value=(
                "# Issue 864\n\n"
                f"{_ISSUE_BODY_MARKER}\n\nWagon graph test content.\n\n"
                f"{_PERSONA_MARKER}\n\nFollow the ATDD lifecycle strictly.\n"
            ),
        ),
        patch(
            "atdd.coach.commands.spawn._build_arch_section",
            return_value=None,
        ),
        patch(
            "atdd.coach.commands.spawn._build_wagon_graph_section",  # does not exist yet → RED
            return_value=_FIXTURE_GRAPH,
        ),
    ):
        prompt_path = spawn._render_launch_prompt(864, worktree)

    content = prompt_path.read_text()
    assert "## Wagon Architecture" in content, (
        "Expected '## Wagon Architecture' in rendered prompt after E026 injection. "
        f"Got:\n{content}"
    )


def test_graph_section_appears_after_issue_body(tmp_path: Path) -> None:
    """The wagon-graph section must appear AFTER the issue body section."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands.session_template import IssueContext

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    with (
        patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"body": "Issue body.\n", "title": "T"},
        ),
        patch(
            "atdd.coach.commands.session_template.build_context",
            return_value=IssueContext(number=864, title="T", worktree_path=str(worktree)),
        ),
        patch(
            "atdd.coach.commands.session_template.render",
            return_value=(
                f"{_ISSUE_BODY_MARKER}\n\nContent.\n\n"
                f"{_PERSONA_MARKER}\n\nWorkflow.\n"
            ),
        ),
        patch("atdd.coach.commands.spawn._build_arch_section", return_value=None),
        patch(
            "atdd.coach.commands.spawn._build_wagon_graph_section",
            return_value=_FIXTURE_GRAPH,
        ),
    ):
        prompt_path = spawn._render_launch_prompt(864, worktree)

    content = prompt_path.read_text()
    body_pos = content.find(_ISSUE_BODY_MARKER)
    graph_pos = content.find("## Wagon Architecture")
    assert graph_pos > body_pos, (
        "Expected wagon-graph section to appear AFTER the issue body section. "
        f"body at {body_pos}, graph at {graph_pos}."
    )


def test_graph_section_appears_before_persona_instructions(tmp_path: Path) -> None:
    """The wagon-graph section must appear BEFORE the persona instructions."""
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
            return_value=IssueContext(number=864, title="T", worktree_path=str(worktree)),
        ),
        patch(
            "atdd.coach.commands.session_template.render",
            return_value=(
                f"{_ISSUE_BODY_MARKER}\n\nContent.\n\n"
                f"{_PERSONA_MARKER}\n\nWorkflow.\n"
            ),
        ),
        patch("atdd.coach.commands.spawn._build_arch_section", return_value=None),
        patch(
            "atdd.coach.commands.spawn._build_wagon_graph_section",
            return_value=_FIXTURE_GRAPH,
        ),
    ):
        prompt_path = spawn._render_launch_prompt(864, worktree)

    content = prompt_path.read_text()
    graph_pos = content.find("## Wagon Architecture")
    persona_pos = content.find(_PERSONA_MARKER)
    assert persona_pos > graph_pos, (
        "Expected wagon-graph section to appear BEFORE the persona instructions. "
        f"graph at {graph_pos}, persona at {persona_pos}."
    )
