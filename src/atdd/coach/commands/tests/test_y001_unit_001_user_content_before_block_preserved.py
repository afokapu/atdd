# Acceptance: acc:self-compliance-migration:Y001-UNIT-001-user-content-before-block-preserved
"""
RED test: atdd sync must preserve user-owned content that appears BEFORE the
ATDD:BEGIN marker.

Bug #581: content outside the managed block was silently removed when sync
re-rendered the managed section.
"""
from pathlib import Path

import pytest

from atdd.coach.commands.sync import AgentConfigSync

BEFORE_CONTENT = "## Rule-ID grammar\n\nCanonical rule IDs use `<archetype>.<convention_short_name>.<rule_name>`.\n\n"


def test_y001_unit_001_user_content_before_block_preserved(tmp_path: Path) -> None:
    """Content before ATDD:BEGIN is byte-for-byte identical after sync."""
    claude_md = tmp_path / "CLAUDE.md"
    existing_block = (
        f"{AgentConfigSync.BLOCK_BEGIN}\n"
        "old managed content\n"
        f"{AgentConfigSync.BLOCK_END}\n"
    )
    claude_md.write_text(BEFORE_CONTENT + existing_block)

    sync = AgentConfigSync(target_dir=tmp_path)
    rc = sync.sync(agents=["claude"])
    assert rc == 0

    result = claude_md.read_text()
    assert result.startswith(BEFORE_CONTENT), (
        "Content before ATDD:BEGIN was modified or removed by sync.\n"
        f"Expected prefix:\n{BEFORE_CONTENT!r}\n"
        f"Actual start:\n{result[:len(BEFORE_CONTENT) + 50]!r}"
    )
