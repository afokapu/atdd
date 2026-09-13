# URN: test:self-compliance:upgrade-refresh:STAMP-UNIT-001-tracked-toolkit-stamp-is-retired
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Runtime: python
"""STAMP-UNIT-001 — nothing writes or reads `toolkit.last_version` (#1989).

    The stamp lives in the untracked per-checkout record and nowhere else.

#1641 moved the toolkit stamp out of the git-tracked `.atdd/config.yaml` into
`.atdd/runtime/toolkit-sync.json`, because a tracked file is reverted by every
checkout, stash and fresh worktree. It kept a read-only fallback to the old field
so repos synced before the change would report a real version, and #1820 dropped
that fallback from `atdd upgrade`. Two bindings to the tracked field survived,
and one of them is a WRITER:

  * `ProjectInitializer._create_config` seeds the field and stamps it forward on
    every `atdd init --force`, so `version_check`'s "Nothing writes it any more"
    is false and any commit taken after such a run re-pins the value. That is
    literally how `3.106.0` got there (`87319e16`, 2026-06-09).
  * `RepoRefresh._apply_branch_protection_on_upgrade` asks "did the toolkit
    upgrade?" of that pinned value, so `_is_newer(installed, 3.106.0)` is
    unconditionally true and every `atdd sync` re-applies branch protection —
    the unconditional remote PUT of #1599, with its cause named.

Measured 2026-09-13: 3 of 102 worktrees carry a record, so the fallback is the
dominant path, not the exception it was kept as.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.commands.initializer import ProjectInitializer
from atdd.coach.commands.sync import RepoRefresh

pytestmark = [pytest.mark.coach]

_PINNED = "3.106.0"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An initialised checkout carrying the pinned tracked stamp."""
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\n"
        f"toolkit:\n  last_version: {_PINNED}\n"
        "github:\n  repo: afokapu/atdd\n"
    )
    return tmp_path


def _config(repo: Path) -> dict:
    return yaml.safe_load((repo / ".atdd" / "config.yaml").read_text()) or {}


# --- the writer -------------------------------------------------------------

def test_create_config_does_not_stamp_the_tracked_field(repo: Path) -> None:
    """`atdd init --force` must not move the stamp forward.

    Today it rewrites the field to the installed version. The write is correct
    and useless: it lands in a file git tracks, so the next checkout reverts it —
    unless someone commits it, which is the mechanism that pinned the value at
    3.106.0 in the first place.

    A value already in an operator's config is left exactly where it is. Deleting
    it is not init's job (see `test_create_config_preserves_operator_values`), and
    it is inert once nothing reads it — which is the rest of this change.
    """
    from atdd import __version__

    ProjectInitializer(repo)._create_config(force=True)

    written = _config(repo)["toolkit"]["last_version"]
    assert written == _PINNED, "init stamped the tracked field forward"
    assert written != __version__


def test_create_config_seeds_no_toolkit_block_in_a_fresh_repo(tmp_path: Path) -> None:
    (tmp_path / ".atdd").mkdir()

    ProjectInitializer(tmp_path)._create_config()

    written = yaml.safe_load((tmp_path / ".atdd" / "config.yaml").read_text()) or {}
    assert "toolkit" not in written


def test_create_config_preserves_operator_values(repo: Path) -> None:
    """Guard: retiring the stamp must not become a config rewrite."""
    ProjectInitializer(repo)._create_config(force=True)

    assert _config(repo)["github"]["repo"] == "afokapu/atdd"


# --- the second reader ------------------------------------------------------

def test_branch_protection_is_not_decided_from_the_tracked_field(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no record, a checkout has not synced under this toolkit.

    The module's own rule is "not first run, not same version". Read from the
    pinned tracked value that rule never fires, and the PUT goes out on every
    single `atdd sync`.
    """
    applied: list = []
    monkeypatch.setattr(
        "atdd.coach.commands.branch_protection.apply_and_verify",
        lambda *a, **k: applied.append((a, k)),
    )

    RepoRefresh(target_dir=repo)._apply_branch_protection_on_upgrade()

    assert applied == []


def test_branch_protection_still_applies_on_a_real_upgrade(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The behaviour being preserved: a checkout whose record predates the
    installed toolkit genuinely did upgrade."""
    from atdd import version_check

    version_check.record_toolkit_sync(repo, version="1.0.0")

    from atdd.coach.commands.branch_protection import ProtectionStatus

    applied: list = []
    monkeypatch.setattr(
        "atdd.coach.commands.branch_protection.apply_and_verify",
        lambda *a, **k: (applied.append((a, k)), (ProtectionStatus.ENFORCED, []))[1],
    )

    RepoRefresh(target_dir=repo)._apply_branch_protection_on_upgrade()

    assert len(applied) == 1
