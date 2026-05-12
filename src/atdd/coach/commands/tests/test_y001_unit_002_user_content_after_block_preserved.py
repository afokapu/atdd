# Acceptance: acc:self-compliance-migration:Y001-UNIT-002-user-content-after-block-preserved
"""
RED test: atdd sync must preserve user-owned content that appears AFTER the
ATDD:END marker.

Bug #581: content outside the managed block was silently removed when sync
re-rendered the managed section.
"""
from pathlib import Path

import pytest

from atdd.coach.commands.sync import AgentConfigSync

AFTER_CONTENT = "\n## bind_rule contract\n\nvalidators MUST call `bind_rule` at module-import time.\n"


def test_y001_unit_002_user_content_after_block_preserved(tmp_path: Path) -> None:
    """Content after ATDD:END is byte-for-byte identical after sync."""
    claude_md = tmp_path / "CLAUDE.md"
    existing_block = (
        f"{AgentConfigSync.BLOCK_BEGIN}\n"
        "old managed content\n"
        f"{AgentConfigSync.BLOCK_END}"
    )
    claude_md.write_text(existing_block + AFTER_CONTENT)

    sync = AgentConfigSync(target_dir=tmp_path)
    rc = sync.sync(agents=["claude"])
    assert rc == 0

    result = claude_md.read_text()
    assert result.endswith(AFTER_CONTENT), (
        "Content after ATDD:END was modified or removed by sync.\n"
        f"Expected suffix:\n{AFTER_CONTENT!r}\n"
        f"Actual end:\n{result[-len(AFTER_CONTENT) - 50:]!r}"
    )
