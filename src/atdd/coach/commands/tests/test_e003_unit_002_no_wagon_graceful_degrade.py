# URN: test:integration-hardening:coach-spawn-wiring:E003-UNIT-002-no-wagon-graceful-degrade
# Acceptance: acc:integration-hardening:E003-UNIT-002-no-wagon-graceful-degrade
# WMBT: wmbt:integration-hardening:E003
# Phase: RED
# Layer: unit
"""E003-UNIT-002 — _render_launch_prompt omits the Architecture context section
and does NOT raise when the issue has no wagon (null wagon field, missing
manifest entry, or entirely absent .atdd/manifest.yaml).

Three sub-cases:
  a) wagon: null in manifest
  b) issue not in manifest at all
  c) no .atdd/manifest.yaml at all (empty repo)
"""
from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


def _minimal_issue_body() -> str:
    return textwrap.dedent("""\
        ## Issue Metadata

        | Field | Value |
        |-------|-------|
        | Branch | `feat/no-wagon-issue` |
        | Train | `TBD` |
        | Feature | none |

        ## Problem

        An issue with no wagon.
    """)


def _run_render(issue_number: int, repo_root: Path, worktree: Path) -> str:
    from atdd.coach.commands import spawn
    from atdd.coach.commands.session_template import IssueContext

    with (
        patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"body": _minimal_issue_body(), "title": "No wagon issue"},
        ),
        patch(
            "atdd.coach.commands.session_template.build_context",
            return_value=IssueContext(
                number=issue_number,
                title="No wagon issue",
                branch="feat/no-wagon-issue",
                worktree_path=str(worktree),
            ),
        ),
        patch(
            "atdd.coach.commands.session_template.render",
            return_value=f"# Issue {issue_number}\n\nSome rendered content.\n",
        ),
    ):
        env_backup = os.environ.get("ATDD_REPO_ROOT")
        os.environ["ATDD_REPO_ROOT"] = str(repo_root)
        try:
            prompt_path = spawn._render_launch_prompt(issue_number, worktree)
        finally:
            if env_backup is None:
                os.environ.pop("ATDD_REPO_ROOT", None)
            else:
                os.environ["ATDD_REPO_ROOT"] = env_backup

    return prompt_path.read_text()


def test_null_wagon_omits_section(tmp_path: Path) -> None:
    """Case (a): wagon: null in manifest → no section, no exception."""
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
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    content = _run_render(901, tmp_path, worktree)

    assert "## Architecture context" not in content, (
        "Section must be absent when wagon is null"
    )


def test_missing_manifest_entry_omits_section(tmp_path: Path) -> None:
    """Case (b): issue not in manifest → no section, no exception."""
    manifest = tmp_path / ".atdd" / "manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        textwrap.dedent("""\
            version: '2.0'
            created: '2026-05-13'
            sessions: []
        """)
    )
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    content = _run_render(902, tmp_path, worktree)

    assert "## Architecture context" not in content, (
        "Section must be absent when issue has no manifest entry"
    )


def test_absent_manifest_omits_section(tmp_path: Path) -> None:
    """Case (c): no .atdd/manifest.yaml → no section, no exception."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    content = _run_render(903, tmp_path, worktree)

    assert "## Architecture context" not in content, (
        "Section must be absent when manifest file is missing"
    )
