# URN: test:self-compliance:upgrade-refresh:UPGRADE-UNIT-001-upgrade-refreshes-in-process
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Runtime: python
"""UPGRADE-UNIT-001 — `atdd upgrade` performs the refresh itself.

    The refresh runs in-process, and a checkout already at the installed version
    is a no-op that shells nothing.

Two defects, one cause. `atdd upgrade` cannot tell whether a refresh is owed, so
it always thinks one is:

  * `_read_sync_record` is per-checkout by design (#1641), and 154 of this
    repository's 157 worktrees have no record. The fallback is the git-tracked
    `toolkit.last_version`, pinned at 3.106.0 while the toolkit ships 4.47.x, so
    `last_version != installed` is permanently true.
  * Believing a refresh is owed, it subprocesses `atdd sync` and then
    `atdd init --force` (upgrader.py:297) — a flag #793 forbids and #1600 shows
    cannot act on an initialised repo anyway.

#1628 already requires an already-current run to be a no-op (E008-UNIT-003); it
cannot be one while the read and the write address different stores.

The refresh is not a separate concern: every job it performs — hooks (#1492),
gitignore (#1325), schemas, the stamp (#1641) — is triggered by a toolkit
version change, which is what `upgrade` exists to detect. So `upgrade` owns it,
and there is no second verb to shell.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands import upgrader as mod


class _Recorder:
    """Stands in for the refresh, recording that it ran."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_a, **_k) -> int:
        self.calls += 1
        return 0


def test_upgrade_refreshes_in_process_without_shelling_a_second_verb(monkeypatch) -> None:
    rec = _Recorder()
    monkeypatch.setattr(mod, "run_repo_refresh", rec, raising=False)

    shelled: list = []
    monkeypatch.setattr(mod.subprocess, "run",
                        lambda *a, **k: shelled.append(a) or _Done())

    mod.Upgrader(repo_root=Path(".")).refresh_repo()

    assert rec.calls == 1, "upgrade must perform the refresh itself"
    assert not shelled, f"upgrade must not shell another verb; shelled {shelled}"


def test_a_checkout_already_at_the_installed_version_is_a_no_op(monkeypatch) -> None:
    """#1628 E008-UNIT-003: already-current means nothing runs."""
    from atdd import __version__

    monkeypatch.setattr(mod, "_read_sync_record", lambda *_a, **_k: __version__)
    rec = _Recorder()
    monkeypatch.setattr(mod, "run_repo_refresh", rec, raising=False)

    assert mod.refresh_is_owed(Path("."), config={}) is False
    assert rec.calls == 0


def test_a_checkout_with_no_record_is_owed_a_refresh(monkeypatch) -> None:
    """The common case: 154 of 157 worktrees carry no record."""
    monkeypatch.setattr(mod, "_read_sync_record", lambda *_a, **_k: None)
    assert mod.refresh_is_owed(Path("."), config={}) is True


def test_the_stale_git_tracked_fallback_is_not_consulted(monkeypatch) -> None:
    """`toolkit.last_version` is pinned at an ancient value in every checkout that
    has one, so consulting it reports a refresh owed forever. #1666 wanted it
    deleted; the premise it cited (the untracked record has shipped) is true in
    code and false in practice, so the fix is to stop reading it, not to trust it."""
    monkeypatch.setattr(mod, "_read_sync_record", lambda *_a, **_k: None)
    owed_with_ancient_fallback = mod.refresh_is_owed(
        Path("."), config={"toolkit": {"last_version": "3.106.0"}}
    )
    owed_without = mod.refresh_is_owed(Path("."), config={})
    assert owed_with_ancient_fallback == owed_without, (
        "the git-tracked fallback must not change the verdict"
    )


class _Done:
    returncode = 0
    stdout = ""
    stderr = ""
