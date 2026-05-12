# Acceptance: acc:self-compliance-migration:Y001-UNIT-003-within-block-deletion-warns
"""
RED test: atdd sync must print a warning when the newly rendered managed block
would remove heading lines that existed in the current file's block.

Bug #581: content added inside the ATDD:BEGIN/END block (e.g. via a persona
template that later changed) was silently stripped on the next atdd sync with
no diff shown, no warning, no opt-in required.
"""
from pathlib import Path

import pytest

from atdd.coach.commands.sync import AgentConfigSync

# Headings that will NEVER appear in the real template — so they are guaranteed
# to be "removed" when sync regenerates the block from the live ATDD.md.
_PHANTOM_HEADING_1 = "## Phantom-Section-581-Alpha"
_PHANTOM_HEADING_2 = "## Phantom-Section-581-Beta"


def _build_file_with_phantom_sections(block_begin: str, block_end: str, tmp_path: Path) -> Path:
    """Write a CLAUDE.md whose managed block contains headings absent from the template."""
    claude_md = tmp_path / "CLAUDE.md"
    content = (
        f"{block_begin}\n"
        f"{_PHANTOM_HEADING_1}\n\n"
        "Content that will not survive the next sync.\n\n"
        f"{_PHANTOM_HEADING_2}\n\n"
        "More ephemeral content.\n"
        f"{block_end}\n"
    )
    claude_md.write_text(content)
    return claude_md


def test_y001_unit_003_within_block_deletion_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """When sync removes headings from the managed block, stdout must warn about them."""
    _build_file_with_phantom_sections(
        AgentConfigSync.BLOCK_BEGIN,
        AgentConfigSync.BLOCK_END,
        tmp_path,
    )

    sync = AgentConfigSync(target_dir=tmp_path)
    rc = sync.sync(agents=["claude"])
    assert rc == 0  # warning is advisory, sync still writes

    out = capsys.readouterr().out
    assert _PHANTOM_HEADING_1 in out, (
        f"Expected a warning mentioning {_PHANTOM_HEADING_1!r} being removed, "
        f"but stdout was:\n{out}"
    )
    assert _PHANTOM_HEADING_2 in out, (
        f"Expected a warning mentioning {_PHANTOM_HEADING_2!r} being removed, "
        f"but stdout was:\n{out}"
    )
