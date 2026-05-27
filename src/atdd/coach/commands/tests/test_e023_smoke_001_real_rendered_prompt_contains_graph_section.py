# URN: test:spawn-agents:E023-SMOKE-001-real-rendered-prompt-contains-graph-section
# Acceptance: acc:spawn-agents:E023-SMOKE-001-real-rendered-prompt-contains-graph-section
# WMBT: wmbt:spawn-agents:E023
# Phase: SMOKE
# Layer: smoke
"""E023-SMOKE-001 — Rendering a launch prompt for a real issue whose wagon is
spawn-agents produces a prompt containing the wagon-graph section (non-empty,
well-formed markdown).

The test calls build_wagon_launch_prompt directly and verifies the returned
string contains '## Wagon Architecture' and is non-empty, since a full
_render_launch_prompt call requires a live GitHub connection (fetch_issue).

Phase RED: fails because build_wagon_launch_prompt does not yet exist in
atdd.coach.commands.issue_graph (ImportError).
Phase GREEN: function exists; the returned section is non-empty and contains
the wagon-graph section heading positioned before the persona section.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.slow]

_REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent


def test_real_wagon_launch_prompt_contains_graph_heading() -> None:
    """build_wagon_launch_prompt('spawn-agents') must contain '## Wagon Architecture'."""
    from atdd.coach.commands.issue_graph import build_wagon_launch_prompt  # type: ignore[import]

    output = build_wagon_launch_prompt("spawn-agents", repo_root=_REPO_ROOT)
    assert output is not None, (
        "build_wagon_launch_prompt returned None for 'spawn-agents'. "
        "Expected a non-None wagon-graph section."
    )
    assert "## Wagon Architecture" in output, (
        "Expected '## Wagon Architecture' heading in the wagon-graph output. "
        f"Got:\n{output}"
    )


def test_real_wagon_launch_prompt_is_non_empty() -> None:
    """The output for spawn-agents must be a non-empty string."""
    from atdd.coach.commands.issue_graph import build_wagon_launch_prompt  # type: ignore[import]

    output = build_wagon_launch_prompt("spawn-agents", repo_root=_REPO_ROOT)
    assert output, "build_wagon_launch_prompt returned empty string for 'spawn-agents'"


def test_real_wagon_launch_prompt_positioned_before_persona_section(tmp_path: Path) -> None:
    """When injected, the wagon-graph section must precede the persona instructions.

    This test uses _render_launch_prompt with all GitHub I/O patched out so it
    can run in SMOKE without network access.  The wagon graph section is NOT
    patched — it must be populated by the real E023 implementation.
    """
    from unittest.mock import patch

    from atdd.coach.commands import spawn
    from atdd.coach.commands.session_template import IssueContext

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    _PERSONA_MARKER = "## Workflow"

    with (
        patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"body": "Real-ish body.\n", "title": "SMOKE issue #864"},
        ),
        patch(
            "atdd.coach.commands.session_template.build_context",
            return_value=IssueContext(
                number=864,
                title="SMOKE issue #864",
                worktree_path=str(worktree),
                wagon="spawn-agents",
            ),
        ),
        patch(
            "atdd.coach.commands.session_template.render",
            return_value=(
                "## Issue context\n\nContent.\n\n"
                f"{_PERSONA_MARKER}\n\nWorkflow steps.\n"
            ),
        ),
        patch("atdd.coach.commands.spawn._build_arch_section", return_value=None),
        # Do NOT patch _build_wagon_graph_section — let the real implementation run.
    ):
        prompt_path = spawn._render_launch_prompt(864, worktree)

    content = prompt_path.read_text()
    assert "## Wagon Architecture" in content, (
        "Expected '## Wagon Architecture' in rendered prompt for wagon 'spawn-agents'. "
        f"Got:\n{content}"
    )
    graph_pos = content.find("## Wagon Architecture")
    persona_pos = content.find(_PERSONA_MARKER)
    assert graph_pos < persona_pos, (
        "Wagon-graph section must appear BEFORE the Workflow section. "
        f"graph at {graph_pos}, persona at {persona_pos}."
    )
