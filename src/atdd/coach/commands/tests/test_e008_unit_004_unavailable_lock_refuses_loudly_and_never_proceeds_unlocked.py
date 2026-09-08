# URN: test:integration-hardening:run-upgrade-unattended:E008-UNIT-004-unavailable-lock-refuses-loudly-and-never-proceeds-unlocked
# Acceptance: acc:integration-hardening:E008-UNIT-004-unavailable-lock-refuses-loudly-and-never-proceeds-unlocked
# WMBT: wmbt:integration-hardening:E008
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-004 — an unavailable lock refuses loudly; it never proceeds unlocked.

RED Test for acc:integration-hardening:E008-UNIT-004-unavailable-lock-refuses-loudly-and-never-proceeds-unlocked
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:E008
Purpose: The posture managed hooks and manifest_migration already set — fail
closed, no bypass env var, refuse the whole run rather than half-do it.
"""
from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from atdd.coach.commands.upgrader import Upgrader

from ._upgrade_unattended_helpers import require_symbol, write_config

pytestmark = [pytest.mark.platform]


@pytest.mark.platform
def test_e008_unit_004_held_lock_refuses_rather_than_mutating(tmp_path, monkeypatch):
    upgrade_lock = require_symbol("upgrade_lock")

    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    holding = threading.Event()
    release = threading.Event()

    def hold():
        with upgrade_lock(timeout=30):
            holding.set()
            release.wait(timeout=30)

    holder = threading.Thread(target=hold)
    holder.start()
    assert holding.wait(timeout=10), "the holder thread never acquired the lock"

    try:
        with patch("atdd.coach.commands.upgrader.__version__", "3.106.0"), \
             patch(
                 "atdd.coach.commands.upgrader.is_outdated",
                 return_value=(True, "3.106.0", "4.27.0"),
             ), \
             patch("atdd.coach.commands.upgrader.auto_upgrade") as mock_upgrade, \
             patch("atdd.coach.commands.upgrader.UPGRADE_LOCK_TIMEOUT", 0.5):
            rc = Upgrader(repo_root=tmp_path).run(yes=True)
    finally:
        release.set()
        holder.join(timeout=10)

    assert rc != 0, "a run that could not take the lock must refuse, not succeed"
    mock_upgrade.assert_not_called()


@pytest.mark.platform
def test_e008_unit_004_refusal_names_the_reason(tmp_path, monkeypatch, capsys):
    upgrade_lock = require_symbol("upgrade_lock")

    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    holding = threading.Event()
    release = threading.Event()

    def hold():
        with upgrade_lock(timeout=30):
            holding.set()
            release.wait(timeout=30)

    holder = threading.Thread(target=hold)
    holder.start()
    assert holding.wait(timeout=10), "the holder thread never acquired the lock"

    try:
        with patch("atdd.coach.commands.upgrader.__version__", "3.106.0"), \
             patch(
                 "atdd.coach.commands.upgrader.is_outdated",
                 return_value=(True, "3.106.0", "4.27.0"),
             ), \
             patch("atdd.coach.commands.upgrader.auto_upgrade"), \
             patch("atdd.coach.commands.upgrader.UPGRADE_LOCK_TIMEOUT", 0.5):
            Upgrader(repo_root=tmp_path).run(yes=True)
    finally:
        release.set()
        holder.join(timeout=10)

    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert any(t in combined for t in ("another", "in progress", "lock")), (
        f"the refusal must name contention as the reason; output was:\n{combined}"
    )
    assert "retry" in combined or "try again" in combined, (
        f"the refusal must say the run can simply be retried; output was:\n{combined}"
    )
