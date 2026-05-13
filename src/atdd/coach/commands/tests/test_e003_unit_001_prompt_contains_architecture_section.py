# URN: test:integration-hardening:coach-spawn-wiring:E003-UNIT-001-prompt-contains-architecture-section
# Acceptance: acc:integration-hardening:E003-UNIT-001-prompt-contains-architecture-section
# WMBT: wmbt:integration-hardening:E003
# Phase: RED
# Layer: unit
"""E003-UNIT-001 — _render_launch_prompt writes '## Architecture context' into
.launch_prompt.txt when the issue has a wagon assigned in .atdd/manifest.yaml.

The section must include:
- wagon URN (wagon:<slug>)
- train ID
- at least one sibling WMBT URN
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


def _make_repo(tmp_path: Path, wagon_slug: str, wmbt_ids: list[str]) -> Path:
    """Scaffold a minimal ATDD repo structure under tmp_path."""
    manifest = tmp_path / ".atdd" / "manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        textwrap.dedent(f"""\
            version: '2.0'
            created: '2026-05-13'
            sessions:
            - id: '900'
              slug: test-issue
              file: null
              issue_number: 900
              type: implementation
              status: RED
              train: 0002-test-train
              wagon: {wagon_slug}
              feature: test-feature
              created: '2026-05-13'
              archived: null
        """)
    )

    wagon_dir = tmp_path / "plan" / wagon_slug.replace("-", "_")
    wagon_dir.mkdir(parents=True)

    wagon_yaml = wagon_dir / f"_{wagon_slug.replace('-', '_')}.yaml"
    wagon_yaml.write_text(
        textwrap.dedent(f"""\
            wagon: {wagon_slug}
            urn: "wagon:{wagon_slug}"
            name: "Test Wagon"
            description: "A test wagon for unit testing."
            theme: commons
            features:
              - urn: "feature:{wagon_slug}:test-feature"
        """)
    )

    for wmbt_id in wmbt_ids:
        wmbt_file = wagon_dir / f"{wmbt_id}.yaml"
        wmbt_file.write_text(
            textwrap.dedent(f"""\
                urn: "wmbt:{wagon_slug}:{wmbt_id}"
                step: "execute"
                direction: "minimize"
                dimension: "time"
                object_of_control: "test-object"
                context_clarifier: "test context"
                lens: "functional.effectiveness"
                statement: "test statement for {wmbt_id}"
                acceptances: []
            """)
        )

    trains_yaml = tmp_path / "plan" / "_trains.yaml"
    trains_yaml.write_text(
        textwrap.dedent(f"""\
            trains:
              0-commons:
                00-commons-nominal:
                  - train_id: "0002-test-train"
                    title: "Test Train"
                    path: "plan/_trains/0002-test-train.yaml"
                    wagons:
                      - first-wagon
                      - {wagon_slug}
                      - last-wagon
        """)
    )

    return tmp_path


def _minimal_issue_body() -> str:
    return textwrap.dedent("""\
        ## Issue Metadata

        | Field | Value |
        |-------|-------|
        | Branch | `feat/test-issue` |
        | Train | `0002-test-train` |
        | Feature | test-feature |

        ## Problem

        A test issue body.
    """)


class _FakeMultiplexer:
    name = "fake"

    def new_surface(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        return "fake-surface"

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        return "fake-workspace"

    def rename_surface(self, ref: str, name: str) -> None:
        pass

    def set_layout(self, ref: str, label: str) -> None:
        pass


def test_prompt_contains_architecture_section(tmp_path: Path) -> None:
    """UNIT-001: rendered prompt includes '## Architecture context'."""
    repo = _make_repo(tmp_path, "test-wagon", ["A001", "B001"])
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    from atdd.coach.commands import spawn

    with (
        patch(
            "atdd.coach.commands.session_template.fetch_issue",
            return_value={"body": _minimal_issue_body(), "title": "Test issue"},
        ),
        patch(
            "atdd.coach.commands.session_template.build_context",
        ) as mock_ctx,
        patch(
            "atdd.coach.commands.session_template.render",
            return_value="# Issue 900\n\nSome rendered content.\n",
        ),
    ):
        from atdd.coach.commands.session_template import IssueContext

        mock_ctx.return_value = IssueContext(
            number=900,
            title="Test issue",
            branch="feat/test-issue",
            train="0002-test-train",
            feature="test-feature",
            worktree_path=str(worktree),
        )

        import os

        env_backup = os.environ.get("ATDD_REPO_ROOT")
        os.environ["ATDD_REPO_ROOT"] = str(repo)
        try:
            prompt_path = spawn._render_launch_prompt(900, worktree)
        finally:
            if env_backup is None:
                os.environ.pop("ATDD_REPO_ROOT", None)
            else:
                os.environ["ATDD_REPO_ROOT"] = env_backup

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
    assert "wmbt:test-wagon:A001" in content or "A001" in content, (
        "Expected at least one sibling WMBT in architecture section"
    )
