"""
Unit tests for the CLI bootstrap path — version_check.print_upgrade_sync_notice.

Issue: #342 — `atdd <any-cmd>` was silently writing `.atdd/config.yaml` and
`atdd.code-workspace` on every invocation through this function. After the
fix, `print_upgrade_sync_notice()` is *warn-only*: it prints the upgrade
banner to stderr and returns without invoking `AgentConfigSync.sync()` or
the toolkit-sync writer (`record_toolkit_sync()` since #1641).

These are unit-resolution tests; the subprocess-resolution sibling lives at
`src/atdd/coach/validators/test_readonly_commands_no_writes.py` and exercises
the same regression through the real CLI entry point.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


def _seed_stale_repo(repo: Path) -> Path:
    """Write a `.atdd/config.yaml` with a stale `toolkit.last_version`.

    Returns the config path.
    """
    atdd_dir = repo / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    config_path = atdd_dir / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """\
            toolkit:
              last_version: 0.0.1
            """
        )
    )
    return config_path


def test_print_upgrade_sync_notice_does_not_call_agent_sync(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`print_upgrade_sync_notice` must not invoke `AgentConfigSync.sync`.

    Regression target for #342: previously the function called sync as a
    side effect of the upgrade banner, mutating CLAUDE.md / CONDUCTOR.md /
    `.atdd/config.yaml` on every CLI invocation.
    """
    _seed_stale_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    from atdd.coach.commands import sync as sync_module

    with patch.object(
        sync_module.AgentConfigSync, "sync", autospec=True, return_value=0
    ) as mock_sync:
        from atdd import version_check

        version_check.print_upgrade_sync_notice()

    assert mock_sync.call_count == 0, (
        "print_upgrade_sync_notice() must not call AgentConfigSync.sync(); "
        "the auto-sync side effect is the bug from issue #342."
    )


def test_print_upgrade_sync_notice_does_not_record_toolkit_sync(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`print_upgrade_sync_notice` must not call `record_toolkit_sync`.

    The version stamp belongs to the explicit `atdd sync` verb, which already
    records the sync at the end of its run. #1641 moved the record out of the
    tracked config into `.atdd/runtime/`, but the read-path invariant is
    unchanged: the check reads, `atdd sync` writes.
    """
    _seed_stale_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    from atdd import version_check

    with patch.object(
        version_check, "record_toolkit_sync", return_value=False
    ) as mock_update:
        version_check.print_upgrade_sync_notice()

    assert mock_update.call_count == 0, (
        "print_upgrade_sync_notice() must not call record_toolkit_sync(); "
        "the write belongs behind `atdd sync` (issues #342, #1641)."
    )


def test_print_upgrade_sync_notice_still_prints_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The warning is the useful part; only the disk write is the bug.

    Decision #1 in issue #342: keep the stderr banner so users still see the
    upgrade signal, just stop the write.
    """
    _seed_stale_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    from atdd import version_check

    # Pin the version. `atdd.__version__` is dynamic (#1172) and resolves to
    # "0.0.0" in a clean checkout, which `check_upgrade_sync_needed` treats as a
    # dev install and stays silent for — so this assertion used to pass only in
    # trees carrying a stale `src/atdd.egg-info` (the #1449 ghost). The banner
    # is what is under test; the ambient version is not.
    monkeypatch.setattr(version_check, "__version__", "9.9.9")

    # Patch the writers so a regression to the old behavior would not pollute
    # the test repo. We do not assert on their call count here — that is
    # covered by the two tests above.
    with patch.object(version_check, "record_toolkit_sync", return_value=False):
        from atdd.coach.commands import sync as sync_module
        with patch.object(
            sync_module.AgentConfigSync, "sync", autospec=True, return_value=0
        ):
            version_check.print_upgrade_sync_notice()

    captured = capsys.readouterr()
    assert "ATDD upgraded" in captured.err or "atdd sync" in captured.err, (
        "Upgrade banner should still print to stderr; only the disk write is "
        f"the bug. Got stderr: {captured.err!r}"
    )


def test_print_upgrade_sync_notice_silent_when_versions_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When `toolkit.last_version` already matches installed, nothing happens.

    No banner, no writes, no calls.
    """
    from atdd import __version__, version_check

    # Seed config at the *current* installed version so no drift fires.
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    (atdd_dir / "config.yaml").write_text(
        f"toolkit:\n  last_version: {__version__}\n"
    )
    monkeypatch.chdir(tmp_path)

    with patch.object(version_check, "record_toolkit_sync", return_value=False) as mock_update:
        from atdd.coach.commands import sync as sync_module
        with patch.object(
            sync_module.AgentConfigSync, "sync", autospec=True, return_value=0
        ) as mock_sync:
            version_check.print_upgrade_sync_notice()

    captured = capsys.readouterr()
    assert captured.err == "", (
        f"No banner expected when versions match; got stderr: {captured.err!r}"
    )
    assert mock_sync.call_count == 0
    assert mock_update.call_count == 0
