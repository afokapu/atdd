"""The toolkit-sync record survives what the tracked field did not (#1641).

The upgrade banner used to read ``toolkit.last_version`` from the git-tracked
``.atdd/config.yaml``. ``atdd sync`` wrote it correctly, but as an uncommitted
edit to a tracked file — so ``git checkout``, ``git stash`` and every fresh
worktree reverted it, and the banner reported the last *committed* value
forever. These tests pin the behaviour that fix depends on.
"""
import json
from pathlib import Path

import pytest

from atdd import version_check
from atdd.version_check import (
    _read_sync_record,
    _sync_record_path,
    check_upgrade_sync_needed,
    record_toolkit_sync,
)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An initialized ATDD repo, cwd'd into, with a known installed version."""
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text("toolkit:\n  last_version: 1.0.0\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(version_check, "__version__", "2.0.0")
    monkeypatch.delenv("CI", raising=False)
    return tmp_path


# --- GT-001: the record round-trips -----------------------------------------

def test_record_round_trips(repo):
    assert record_toolkit_sync(repo) is True
    assert _read_sync_record(repo) == "2.0.0"


def test_record_lands_under_gitignored_runtime_dir(repo):
    record_toolkit_sync(repo)
    rel = _sync_record_path(repo).relative_to(repo)
    # `.atdd/runtime/` is gitignored; `.atdd/cache/` is a cache a clean may drop.
    assert rel == Path(".atdd") / "runtime" / "toolkit-sync.json"


def test_absent_record_reads_as_none(repo):
    assert _read_sync_record(repo) is None


def test_corrupt_record_reads_as_none_rather_than_raising(repo):
    path = _sync_record_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert _read_sync_record(repo) is None


# --- GT-002: survives the operations that reverted the tracked field --------

def test_record_survives_a_git_checkout(repo):
    """The regression that started it all.

    A tracked-file stamp is reverted by checkout. An ignored one is not — so
    this test simulates the revert by restoring config.yaml to its committed
    contents and asserting the banner stays quiet anyway.
    """
    record_toolkit_sync(repo)
    # What `git checkout` does to the tracked config: back to the committed value.
    (repo / ".atdd" / "config.yaml").write_text("toolkit:\n  last_version: 1.0.0\n")

    assert check_upgrade_sync_needed() is None


def test_banner_quiet_when_record_matches_installed(repo):
    record_toolkit_sync(repo)
    assert check_upgrade_sync_needed() is None


# --- GT-003: the from-version is the version actually synced ----------------

def test_banner_reports_the_recorded_version_as_from(repo):
    record_toolkit_sync(repo, version="1.9.0")

    msg = check_upgrade_sync_needed()

    assert msg is not None
    assert "1.9.0 → 2.0.0" in msg
    # Never the stale tracked value.
    assert "1.0.0" not in msg


def test_record_ahead_of_installed_stays_quiet(repo):
    record_toolkit_sync(repo, version="3.0.0")
    assert check_upgrade_sync_needed() is None


# --- GT-004: one-time fallback to the legacy tracked field ------------------

def test_falls_back_to_legacy_field_when_no_record(repo):
    msg = check_upgrade_sync_needed()

    assert msg is not None
    assert "1.0.0 → 2.0.0" in msg


def test_legacy_fallback_does_not_write(repo):
    """#342: the check runs on every invocation, including `atdd --help`.

    Adopting the legacy value here would put a write back on the read path.
    Migration is `atdd sync`'s job.
    """
    check_upgrade_sync_needed()

    assert not _sync_record_path(repo).exists()


def test_atdd_repo_without_any_version_asks_for_sync_without_inventing_a_from(repo):
    (repo / ".atdd" / "config.yaml").write_text("toolkit: {}\n")

    msg = check_upgrade_sync_needed()

    assert msg == "ATDD upgraded to 2.0.0. Run: atdd sync && atdd init"
    assert "→" not in msg


def test_non_atdd_repo_stays_silent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(version_check, "__version__", "2.0.0")
    monkeypatch.delenv("CI", raising=False)

    assert check_upgrade_sync_needed() is None


# --- hot path ---------------------------------------------------------------

def test_matching_record_short_circuits_before_any_yaml_parse(repo, monkeypatch):
    """The check runs on every CLI invocation; the common case must not pay
    for a pure-Python yaml.safe_load of the whole config."""
    record_toolkit_sync(repo)

    def _boom(*_args, **_kwargs):
        raise AssertionError("config.yaml was parsed on the fast path")

    monkeypatch.setattr(version_check, "_load_repo_config", _boom)

    assert check_upgrade_sync_needed() is None


def test_dev_install_never_nags(repo, monkeypatch):
    monkeypatch.setattr(version_check, "__version__", "0.0.0")
    assert check_upgrade_sync_needed() is None


def test_record_contents_are_a_readable_json_object(repo):
    record_toolkit_sync(repo)

    data = json.loads(_sync_record_path(repo).read_text())

    assert data["last_synced_version"] == "2.0.0"
    assert isinstance(data["synced_at"], int)


def test_recording_never_creates_an_atdd_tree(tmp_path, monkeypatch):
    """`atdd sync` is a refresher, not an installer.

    Writing the record must not conjure `.atdd/` in a repo that never ran
    `atdd init` — the invariant the predecessor got for free by requiring an
    existing config.yaml.
    """
    monkeypatch.setattr(version_check, "__version__", "2.0.0")

    assert record_toolkit_sync(tmp_path) is False
    assert not (tmp_path / ".atdd").exists()
