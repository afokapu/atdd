"""
RED tests for issue #581: atdd sync silently strips externally-added content.

Scenario: a prior PR added sections to the managed block (e.g. ## Rule-ID grammar)
that are not part of the current template/overlay. A subsequent `atdd sync` must NOT
silently remove those lines. It should warn and refuse unless --force is passed.

Run:
    PYTHONPATH=src python3 -m pytest -q \
        src/atdd/coach/commands/tests/test_sync_preserve_managed_content.py -v
"""
from pathlib import Path

import pytest

from atdd.coach.commands.sync import AgentConfigSync


BLOCK_BEGIN = AgentConfigSync.BLOCK_BEGIN
BLOCK_END = AgentConfigSync.BLOCK_END

_EXTRA_SECTION = "## Rule-ID grammar\n\nExtra content added by external PR.\n"


def _file_with_extra_in_block(tmp_path: Path, agent: str) -> Path:
    """Write an agent file that has extra lines inside the managed block."""
    sync = AgentConfigSync(target_dir=tmp_path)
    # First sync: creates the file with only the canonical block
    sync.sync(agents=[agent])

    filename = AgentConfigSync.AGENT_FILES[agent]
    agent_path = tmp_path / filename

    content = agent_path.read_text()
    # Inject extra section just before ATDD:END
    injected = content.replace(BLOCK_END, _EXTRA_SECTION + "\n" + BLOCK_END)
    agent_path.write_text(injected)
    return agent_path


def test_sync_without_force_does_not_strip_extra_content(tmp_path: Path) -> None:
    """Without --force, sync must NOT remove lines present in managed block but absent from template."""
    agent_path = _file_with_extra_in_block(tmp_path, "claude")

    sync = AgentConfigSync(target_dir=tmp_path)
    rc = sync.sync(agents=["claude"])  # no force

    # Should abort / return non-zero when net deletion detected
    assert rc != 0, "sync should fail (non-zero) when it would strip extra content without --force"

    # The extra section must still be in the file (no destructive write)
    content = agent_path.read_text()
    assert _EXTRA_SECTION.splitlines()[0] in content, \
        "extra content must NOT be stripped without --force"


def test_sync_with_force_removes_extra_content(tmp_path: Path) -> None:
    """With --force, sync may remove extra lines and returns 0."""
    agent_path = _file_with_extra_in_block(tmp_path, "claude")

    sync = AgentConfigSync(target_dir=tmp_path)
    rc = sync.sync(agents=["claude"], force=True)

    assert rc == 0, "sync --force should succeed"

    content = agent_path.read_text()
    # The extra section should be gone (force-overwritten)
    assert _EXTRA_SECTION.splitlines()[0] not in content, \
        "--force should allow stripping extra content"


def test_sync_warns_about_removed_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Without --force, sync must print a warning naming the would-be-deleted content."""
    _file_with_extra_in_block(tmp_path, "claude")

    sync = AgentConfigSync(target_dir=tmp_path)
    sync.sync(agents=["claude"])  # no force

    out = capsys.readouterr().out + capsys.readouterr().err
    assert "Rule-ID grammar" in out or "would remove" in out or "force" in out, \
        "warning output must mention removed content or --force flag"


def test_sync_no_deletion_proceeds_without_force(tmp_path: Path) -> None:
    """When the new block is a superset (no deletions), sync proceeds without --force."""
    sync = AgentConfigSync(target_dir=tmp_path)
    rc = sync.sync(agents=["claude"])
    assert rc == 0, "clean sync (no deletions) should succeed without --force"

    # Second sync on already-synced file: no deletions → should still be 0
    rc2 = sync.sync(agents=["claude"])
    assert rc2 == 0, "idempotent sync should succeed"


def test_sync_outside_block_content_always_preserved(tmp_path: Path) -> None:
    """Content before ATDD:BEGIN and after ATDD:END is always preserved regardless of --force."""
    sync = AgentConfigSync(target_dir=tmp_path)
    sync.sync(agents=["claude"])

    claude_md = tmp_path / "CLAUDE.md"
    content = claude_md.read_text()

    prefix = "# My custom header\n\n"
    suffix = "\n\n## My trailing notes\n"
    # Write with user content outside the block
    claude_md.write_text(prefix + content + suffix)

    rc = sync.sync(agents=["claude"])
    # Even if rc is non-zero (due to extra inside block), outside content must survive
    final = claude_md.read_text()
    assert "My custom header" in final, "content before ATDD:BEGIN must always be preserved"
    assert "My trailing notes" in final, "content after ATDD:END must always be preserved"
