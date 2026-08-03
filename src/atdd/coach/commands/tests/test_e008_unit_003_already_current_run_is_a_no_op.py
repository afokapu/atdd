# URN: test:integration-hardening:run-upgrade-unattended:E008-UNIT-003-already-current-run-is-a-no-op
# Acceptance: acc:integration-hardening:E008-UNIT-003-already-current-run-is-a-no-op
# WMBT: wmbt:integration-hardening:E008
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-003 — an already-current run mutates nothing.

RED Test for acc:integration-hardening:E008-UNIT-003-already-current-run-is-a-no-op
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:E008
Purpose: Idempotency. The fifty-nine agents arriving after an upgrade cost one
check each, not fifty-nine mutations.

TESTER NOTE (#1628): a regression guard, not a first-failing test. Today's
Upgrader already short-circuits on `last_version == installed`, so this passes
against the unfixed implementation. It is here because the E008 lock rework
touches exactly this path and could plausibly break it — a run that takes a
lock and re-syncs when there is nothing to do would still look "correct" to
every other test in this feature.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atdd.coach.commands.upgrader import Upgrader

from ._upgrade_unattended_helpers import exploding_input, write_config

pytestmark = [pytest.mark.platform]


@pytest.mark.platform
def test_e008_unit_003_no_mutation_when_already_current(tmp_path, monkeypatch, capsys):
    write_config(tmp_path, last_version="4.27.0")
    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.commands.upgrader.__version__", "4.27.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             return_value=(False, "4.27.0", "4.27.0"),
         ), \
         patch("atdd.coach.commands.upgrader.auto_upgrade") as mock_upgrade, \
         patch("atdd.coach.commands.upgrader.subprocess.run") as mock_run, \
         patch("sys.stdin.isatty", return_value=False), \
         patch("builtins.input", side_effect=exploding_input):
        rc = Upgrader(repo_root=tmp_path).run(yes=False)

    assert rc == 0, f"an already-current run must succeed, got {rc}"
    mock_upgrade.assert_not_called()
    mock_run.assert_not_called()
    assert "already in sync" in capsys.readouterr().out.lower()


@pytest.mark.platform
def test_e008_unit_003_repeating_it_changes_nothing(tmp_path, monkeypatch):
    write_config(tmp_path, last_version="4.27.0")
    monkeypatch.chdir(tmp_path)

    codes = []
    for _ in range(2):
        with patch("atdd.coach.commands.upgrader.__version__", "4.27.0"), \
             patch(
                 "atdd.coach.commands.upgrader.is_outdated",
                 return_value=(False, "4.27.0", "4.27.0"),
             ), \
             patch("atdd.coach.commands.upgrader.auto_upgrade") as mock_upgrade, \
             patch("atdd.coach.commands.upgrader.subprocess.run") as mock_run, \
             patch("sys.stdin.isatty", return_value=False), \
             patch("builtins.input", side_effect=exploding_input):
            codes.append(Upgrader(repo_root=tmp_path).run(yes=False))
            mock_upgrade.assert_not_called()
            mock_run.assert_not_called()

    assert codes == [0, 0], f"repeated no-op runs must converge; got {codes}"
