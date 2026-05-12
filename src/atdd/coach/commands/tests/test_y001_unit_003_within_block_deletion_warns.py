# Acceptance: acc:self-compliance-migration:Y001-UNIT-003-within-block-deletion-warns
"""
RED test: atdd sync must print a warning when the newly rendered managed block
would remove heading lines that existed in the current file's block.

Bug #581: PR #561 added ## Rule-ID grammar and ## bind_rule contract sections
inside the ATDD:BEGIN/END block; a subsequent atdd sync silently stripped them
without any warning or diff shown.
"""
from pathlib import Path

import pytest

from atdd.coach.commands.sync import AgentConfigSync


def _build_file_with_extra_sections(block_begin: str, block_end: str, tmp_path: Path) -> Path:
    """Write a CLAUDE.md whose managed block contains headings not in the template."""
    claude_md = tmp_path / "CLAUDE.md"
    content = (
        f"{block_begin}\n"
        "## Existing Template Section\n\n"
        "Some template content.\n\n"
        "## Rule-ID grammar\n\n"
        "Canonical rule IDs use `<archetype>.<convention_short_name>.<rule_name>`.\n\n"
        "## bind_rule contract\n\n"
        "validators MUST call `bind_rule` at module-import time.\n"
        f"{block_end}\n"
    )
    claude_md.write_text(content)
    return claude_md


def test_y001_unit_003_within_block_deletion_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """When sync removes headings from the managed block, stdout must warn about them."""
    _build_file_with_extra_sections(
        AgentConfigSync.BLOCK_BEGIN,
        AgentConfigSync.BLOCK_END,
        tmp_path,
    )

    sync = AgentConfigSync(target_dir=tmp_path)
    rc = sync.sync(agents=["claude"])
    assert rc == 0  # warning is advisory, sync still writes

    out = capsys.readouterr().out
    assert "## Rule-ID grammar" in out or "Rule-ID grammar" in out, (
        "Expected a warning mentioning '## Rule-ID grammar' being removed from the "
        f"managed block, but stdout was:\n{out}"
    )
    assert "## bind_rule contract" in out or "bind_rule contract" in out, (
        "Expected a warning mentioning '## bind_rule contract' being removed from the "
        f"managed block, but stdout was:\n{out}"
    )
