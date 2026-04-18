"""
Platform tests: `atdd sync` renders custom themes in the CLAUDE.md block.

Issue: #291 Phase 4 (REFACTOR) deliverable.

When `.atdd/config.yaml` declares a `themes:` block, the managed ATDD
section written by `atdd sync` must include a `# Theme map` comment
listing the merged digit→name mapping. When no overrides exist, the
section is omitted (keeps CLAUDE.md deterministic for repos that
opted out).

URN: test:coach:custom-themes:sync-block
"""
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(repo: Path, themes: dict | None) -> None:
    repo.joinpath(".atdd").mkdir(parents=True, exist_ok=True)
    cfg = {
        "version": "1.0",
        "release": {"version_file": "pyproject.toml", "tag_prefix": "v"},
        "sync": {"agents": ["claude"]},
    }
    if themes is not None:
        cfg["themes"] = themes
    (repo / ".atdd" / "config.yaml").write_text(yaml.safe_dump(cfg))


# ---------------------------------------------------------------------------
# Rendering behavior
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_theme_section_is_empty_without_overrides(tmp_path):
    """
    SPEC-COACH-SYNC-THEMES-0001: No overrides → no theme section.

    Backward compatibility: the ATDD block written by `atdd sync` into
    CLAUDE.md must not drift for repos that have not opted in to
    custom themes.
    """
    from atdd.coach.commands.sync import AgentConfigSync

    _write_config(tmp_path, themes=None)
    sync = AgentConfigSync(target_dir=tmp_path)

    section = sync._render_theme_map_section()

    assert section == "", (
        f"Expected empty theme section when no overrides configured, "
        f"got: {section!r}"
    )


@pytest.mark.platform
def test_theme_section_renders_merged_mapping_when_overrides_present(tmp_path):
    """
    SPEC-COACH-SYNC-THEMES-0002: Overrides → rendered block lists the merge.

    The pluggy fixture (from issue body) declares 3 overrides. The
    rendered section must include each override's digit → custom name
    alongside the original default for operator cross-reference.
    """
    from atdd.coach.commands.sync import AgentConfigSync

    _write_config(
        tmp_path,
        themes={"1": "qualification", "2": "security", "3": "operations"},
    )
    sync = AgentConfigSync(target_dir=tmp_path)

    section = sync._render_theme_map_section()

    assert section.startswith("# Theme map"), (
        f"Section must start with `# Theme map` header, got: {section!r}"
    )
    assert "1: qualification" in section
    assert "2: security" in section
    assert "3: operations" in section
    assert "default was mechanic" in section
    assert "default was scenario" in section
    assert "default was match" in section
    assert "0: commons" in section, "Unoverridden digits still listed"


@pytest.mark.platform
def test_theme_section_is_included_inside_managed_block(tmp_path):
    """
    SPEC-COACH-SYNC-THEMES-0003: Section appears inside BEGIN/END markers.

    The renderer must place the theme block between the ATDD BEGIN and
    END markers so consumers reading CLAUDE.md see it as part of the
    managed block, not free-form content.
    """
    from atdd.coach.commands.sync import AgentConfigSync

    _write_config(tmp_path, themes={"1": "qualification"})
    sync = AgentConfigSync(target_dir=tmp_path)

    rendered = sync._generate_block("claude", "base atdd content placeholder")

    begin_idx = rendered.index(sync.BLOCK_BEGIN)
    end_idx = rendered.index(sync.BLOCK_END)
    theme_idx = rendered.index("# Theme map")

    assert begin_idx < theme_idx < end_idx, (
        "Theme map section must appear between BLOCK_BEGIN and BLOCK_END"
    )
