"""
RED tests for #280 D001 — atdd issue <slug> renders a template-seeded body.

WMBT: wmbt:govern-lifecycle:D001 — acc:govern-lifecycle:D001-UNIT-001-template-seed-on-create

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/commands/tests/test_parent_body_template_seed.py -v
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_manager(tmp_path: Path):
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "github:\n  repo: afokapu/atdd\n",
        encoding="utf-8",
    )
    from atdd.coach.commands.issue import IssueManager
    return IssueManager(target_dir=tmp_path)


def test_d001_rendered_body_seeds_branch_from_slug_and_type(tmp_path):
    """D001: rendered body must seed the Branch field to `{prefix}/{slug}`
    based on issue_type, not leave it as TBD.
    """
    manager = _make_manager(tmp_path)

    body = manager._render_parent_body(
        slug="my-feature",
        issue_type="implementation",
        today="2026-04-14",
        train_display="TBD",
        archetypes_display="coach",
    )

    assert "| Branch | `feat/my-feature` |" in body, (
        "Branch field must be seeded to feat/my-feature, not left as TBD. "
        "Current template hardcodes 'Branch | TBD <!-- fmt: ... -->'."
    )


def test_d001_rendered_body_uses_fix_prefix_for_refactor_type(tmp_path):
    """D001: refactor issues seed Branch with `refactor/` prefix."""
    manager = _make_manager(tmp_path)

    body = manager._render_parent_body(
        slug="bug-fix",
        issue_type="refactor",
        today="2026-04-14",
        train_display="TBD",
        archetypes_display="coach",
    )

    assert "| Branch | `refactor/bug-fix` |" in body


def test_d001_rendered_body_contains_dependencies_heading(tmp_path):
    """D001: rendered body must contain a '### Dependencies' heading so
    the coach can parse the dep graph without post-hoc edits.
    """
    manager = _make_manager(tmp_path)

    body = manager._render_parent_body(
        slug="any-slug",
        issue_type="implementation",
        today="2026-04-14",
        train_display="TBD",
        archetypes_display="coach",
    )

    assert "### Dependencies" in body


def test_d001_rendered_body_is_template_compliant(tmp_path):
    """D001: rendered body must contain all four headings the check validator
    requires: Issue Metadata, Phases, Validation, Activity Log, Artifacts.
    """
    manager = _make_manager(tmp_path)

    body = manager._render_parent_body(
        slug="any-slug",
        issue_type="implementation",
        today="2026-04-14",
        train_display="0001-demo",
        archetypes_display="coach",
    )

    for heading in ("## Issue Metadata", "## Phases", "## Validation",
                    "## Activity Log", "## Artifacts"):
        assert heading in body, f"rendered body missing {heading!r}"
