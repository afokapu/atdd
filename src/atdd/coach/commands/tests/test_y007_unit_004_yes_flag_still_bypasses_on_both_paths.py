# URN: test:integration-hardening:run-upgrade-unattended:Y007-UNIT-004-yes-flag-still-bypasses-on-both-paths
# Acceptance: acc:integration-hardening:Y007-UNIT-004-yes-flag-still-bypasses-on-both-paths
# WMBT: wmbt:integration-hardening:Y007
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""Y007-UNIT-004 — --yes keeps bypassing both prompts, TTY or not.

RED Test for acc:integration-hardening:Y007-UNIT-004-yes-flag-still-bypasses-on-both-paths
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:Y007
Purpose: The pre-existing escape hatch keeps working and keeps winning, so the
TTY inference never overrides an explicit flag.

TESTER NOTE (#1628): this is a regression guard, not a first-failing test. With
yes=True today's code already skips both prompts, so all four combinations pass
against the unfixed implementation. It is here to stay green through GREEN, not
to go green at GREEN.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atdd.coach.commands.upgrader import Upgrader

from ._upgrade_unattended_helpers import exploding_input, write_config

pytestmark = [pytest.mark.platform]


class _Ok:
    returncode = 0


@pytest.mark.platform
@pytest.mark.parametrize("isatty", [True, False], ids=["tty", "no-tty"])
def test_y007_unit_004_yes_bypasses_pypi_prompt(tmp_path, monkeypatch, isatty):
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.commands.upgrader.__version__", "3.106.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             return_value=(True, "3.106.0", "4.27.0"),
         ), \
         patch("atdd.coach.commands.upgrader.auto_upgrade", return_value=True), \
         patch("sys.stdin.isatty", return_value=isatty), \
         patch("builtins.input", side_effect=exploding_input):
        rc = Upgrader(repo_root=tmp_path).run(yes=True)

    assert rc == 0, f"--yes must complete regardless of isatty={isatty}, got {rc}"


@pytest.mark.platform
@pytest.mark.parametrize("isatty", [True, False], ids=["tty", "no-tty"])
def test_y007_unit_004_yes_bypasses_sync_prompt(tmp_path, monkeypatch, isatty):
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.commands.upgrader.__version__", "4.27.0"), \
         patch("atdd.coach.commands.upgrader.subprocess.run", return_value=_Ok()), \
         patch("sys.stdin.isatty", return_value=isatty), \
         patch("builtins.input", side_effect=exploding_input):
        rc = Upgrader(repo_root=tmp_path).run(yes=True, no_pypi=True)

    assert rc == 0, f"--yes must complete regardless of isatty={isatty}, got {rc}"
