# URN: test:integration-hardening:coach-spawn-wiring:E003-UNIT-002-no-wagon-graceful-degrade
# Acceptance: acc:integration-hardening:E003-UNIT-002-no-wagon-graceful-degrade
# WMBT: wmbt:integration-hardening:E003
# Phase: RED
# Layer: unit
"""E003-UNIT-002 — _render_launch_prompt omits the Architecture context section
and does NOT raise when _build_arch_section returns None (which happens when
the issue has no wagon assigned).

Also tests the underlying build_issue_architecture_context() directly with
explicit repo_root to verify the three no-wagon sub-cases:
  a) wagon: null in manifest
  b) issue not in manifest at all
  c) no .atdd/manifest.yaml at all (empty repo)
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Spawn integration tests (patch _build_arch_section → None)
# ---------------------------------------------------------------------------


def test_spawn_omits_section_when_build_returns_none(tmp_path: Path) -> None:
    """_render_launch_prompt omits the section when _build_arch_section returns None."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    from atdd.coach.commands import spawn
    from atdd.coach.commands.session_template import IssueContext

    with (
        patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"body": "", "title": "No wagon issue"},
        ),
        patch(
            "atdd.coach.commands.session_template.build_context",
            return_value=IssueContext(
                number=901,
                title="No wagon issue",
                worktree_path=str(worktree),
            ),
        ),
        patch(
            "atdd.coach.commands.session_template.render",
            return_value="# Issue 901\n\nSome rendered content.\n",
        ),
        patch(
            "atdd.coach.commands.spawn._build_arch_section",
            return_value=None,
        ),
    ):
        prompt_path = spawn._render_launch_prompt(901, worktree)

    content = prompt_path.read_text()

    assert "## Architecture context" not in content, (
        "Section must be absent when _build_arch_section returns None"
    )


# ---------------------------------------------------------------------------
# build_issue_architecture_context unit tests (explicit repo_root, no env)
# ---------------------------------------------------------------------------


def test_null_wagon_returns_none(tmp_path: Path) -> None:
    """Case (a): wagon: null in manifest → returns None."""
    manifest = tmp_path / ".atdd" / "manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        textwrap.dedent("""\
            version: '2.0'
            created: '2026-05-13'
            sessions:
            - id: '901'
              slug: no-wagon-issue
              file: null
              issue_number: 901
              type: implementation
              status: INIT
              wagon: null
              train: null
              created: '2026-05-13'
              archived: null
        """)
    )

    from atdd.coach.commands.issue_graph import build_issue_architecture_context

    result = build_issue_architecture_context(901, repo_root=tmp_path)

    assert result is None, "Expected None when wagon field is null"


def test_missing_manifest_entry_returns_none(tmp_path: Path) -> None:
    """Case (b): issue not in manifest → returns None."""
    manifest = tmp_path / ".atdd" / "manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        textwrap.dedent("""\
            version: '2.0'
            created: '2026-05-13'
            sessions: []
        """)
    )

    from atdd.coach.commands.issue_graph import build_issue_architecture_context

    result = build_issue_architecture_context(902, repo_root=tmp_path)

    assert result is None, "Expected None when issue has no manifest entry"


def test_absent_manifest_returns_none(tmp_path: Path) -> None:
    """Case (c): no .atdd/manifest.yaml → returns None."""
    from atdd.coach.commands.issue_graph import build_issue_architecture_context

    result = build_issue_architecture_context(903, repo_root=tmp_path)

    assert result is None, "Expected None when manifest file is absent"
