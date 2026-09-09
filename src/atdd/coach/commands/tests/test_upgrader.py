"""
Unit tests for `atdd upgrade` (Upgrader).

Regression for #277: `atdd upgrade` reported "Already up to date" when a newer
atdd release was available on PyPI because Upgrader only compared the installed
version against the local `toolkit.last_version` stamp and never queried PyPI.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.coach.commands.upgrader import Upgrader

pytestmark = [pytest.mark.platform]


def _write_config(repo: Path, last_version: str) -> Path:
    """Seed a repo at *last_version*.

    #1762: delegates to the shared helper rather than repeating the seeding
    block. Both files wrote the same `.atdd/runtime/toolkit-sync.json` after
    #1820 moved the baseline off the git-tracked field, which is exactly the
    duplication `coder.refactor.quality-duplication` exists to catch.
    """
    from atdd.coach.commands.tests._upgrade_unattended_helpers import write_config

    return write_config(repo, last_version)

def test_upgrade_detects_newer_pypi_release(tmp_path, monkeypatch, capsys):
    """When PyPI reports a newer version, upgrade should offer pip install."""
    _write_config(tmp_path, last_version="1.49.0")
    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.commands.upgrader.__version__", "1.49.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             return_value=(True, "1.49.0", "1.53.0"),
         ), \
         patch(
             "atdd.coach.commands.upgrader.auto_upgrade",
             return_value=(True, ""),
         ) as mock_upgrade:
        rc = Upgrader(repo_root=tmp_path).run(yes=True)

    out = capsys.readouterr().out
    assert rc == 0
    assert "1.49.0 → 1.53.0" in out
    mock_upgrade.assert_called_once()
    assert "Re-run `atdd upgrade`" in out


def test_upgrade_no_pypi_flag_skips_live_check(tmp_path, monkeypatch, capsys):
    """--no-pypi must bypass is_outdated() entirely."""
    _write_config(tmp_path, last_version="1.49.0")
    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.commands.upgrader.__version__", "1.49.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             side_effect=AssertionError("must not be called when no_pypi=True"),
         ), \
         patch(
             "atdd.coach.commands.upgrader.auto_upgrade",
             side_effect=AssertionError("must not pip-upgrade under --no-pypi"),
         ):
        rc = Upgrader(repo_root=tmp_path).run(yes=True, no_pypi=True)

    out = capsys.readouterr().out
    assert rc == 0
    assert "Already current with the installed version." in out


def test_upgrade_pypi_unreachable_falls_back_to_sync(tmp_path, monkeypatch, capsys):
    """If is_outdated() returns latest=None, skip PyPI step and continue sync."""
    _write_config(tmp_path, last_version="1.49.0")
    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.commands.upgrader.__version__", "1.49.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             return_value=(False, "1.49.0", ""),
         ):
        rc = Upgrader(repo_root=tmp_path).run(yes=True)

    out = capsys.readouterr().out
    assert rc == 0
    assert "Could not reach PyPI" in out
    assert "Already current with the installed version." in out


def test_upgrade_already_latest_runs_sync_only(tmp_path, monkeypatch, capsys):
    """When installed == PyPI latest but stamp is stale, run sync without pip upgrade."""
    _write_config(tmp_path, last_version="1.50.0")
    monkeypatch.chdir(tmp_path)

    ran_subprocess: list = []

    def fake_run(cmd, cwd=None):
        ran_subprocess.append(cmd)

        class R:
            returncode = 0

        return R()

    with patch("atdd.coach.commands.upgrader.__version__", "1.53.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             return_value=(False, "1.53.0", "1.53.0"),
         ), \
         patch(
             "atdd.coach.commands.upgrader.auto_upgrade",
             side_effect=AssertionError("must not pip-upgrade when already latest"),
         ), \
         patch("atdd.coach.commands.upgrader.subprocess.run", side_effect=fake_run), \
         patch("atdd.coach.commands.upgrader.run_repo_refresh",
               side_effect=lambda *_a, **_k: ran_subprocess.append("refresh") or 0):
        rc = Upgrader(repo_root=tmp_path).run(yes=True)

    assert rc == 0
    # #1820: the refresh runs in-process. It used to shell `atdd sync` then
    # `atdd init --force`; the latter is forbidden (#793) and, per #1600, cannot
    # act on an already-initialised repo.
    assert any("refresh" in c for c in ran_subprocess), ran_subprocess
