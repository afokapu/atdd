# URN: test:integration-hardening:coach-spawn-wiring:E003-UNIT-001-prompt-contains-architecture-section
# Acceptance: acc:integration-hardening:E003-UNIT-001-prompt-contains-architecture-section
# WMBT: wmbt:integration-hardening:E003
# Phase: RED
# Layer: unit
"""E003-UNIT-001 — _render_launch_prompt splices '## Architecture context' into
.launch_prompt.txt when _build_arch_section returns a non-None section.

The section must include the wagon URN, train ID, and sibling WMBT URNs.
_build_arch_section is patched to a fixed return value so the test is
isolated from manifest I/O and env-var mutation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]

_ARCH_SECTION = (
    "## Architecture context\n\n"
    "**Wagon:** `wagon:test-wagon` — Test Wagon\n"
    "> A test wagon.\n\n"
    "**Train:** `0002-test-train`\n"
    "**Wagon order:** alpha → test-wagon → omega (position 2/3)\n\n"
    "**Sibling WMBTs in this wagon:**\n"
    "- `wmbt:test-wagon:A001`\n"
    "- `wmbt:test-wagon:B001`\n\n"
)


def test_prompt_contains_architecture_section(tmp_path: Path) -> None:
    """UNIT-001: rendered prompt includes '## Architecture context'."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    from atdd.coach.commands import spawn
    from atdd.coach.commands.session_template import IssueContext

    with (
        patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"body": "", "title": "Test issue"},
        ),
        patch(
            "atdd.coach.commands.session_template.build_context",
            return_value=IssueContext(
                number=900,
                title="Test issue",
                worktree_path=str(worktree),
            ),
        ),
        patch(
            "atdd.coach.commands.session_template.render",
            return_value="# Issue 900\n\nSome rendered content.\n",
        ),
        patch(
            "atdd.coach.commands.spawn._build_arch_section",
            return_value=_ARCH_SECTION,
        ),
    ):
        prompt_path = spawn._render_launch_prompt(900, worktree)

    content = prompt_path.read_text()

    assert "## Architecture context" in content, (
        "Expected '## Architecture context' section in launch prompt"
    )
    assert "wagon:test-wagon" in content, (
        "Expected wagon URN 'wagon:test-wagon' in architecture section"
    )
    assert "0002-test-train" in content, (
        "Expected train ID '0002-test-train' in architecture section"
    )
    assert "wmbt:test-wagon:A001" in content, (
        "Expected sibling WMBT in architecture section"
    )
