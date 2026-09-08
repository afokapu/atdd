# URN: test:integration-hardening:run-upgrade-unattended:Y007-UNIT-001-no-tty-pypi-prompt-resolves-without-input
# Acceptance: acc:integration-hardening:Y007-UNIT-001-no-tty-pypi-prompt-resolves-without-input
# WMBT: wmbt:integration-hardening:Y007
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""Y007-UNIT-001 — a no-TTY run reaches the upgrade decision without input().

RED Test for acc:integration-hardening:Y007-UNIT-001-no-tty-pypi-prompt-resolves-without-input
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:Y007
Purpose: With stdin not a terminal and a newer version on PyPI, Upgrader.run()
must resolve its confirmation without calling input() — the exact site
(upgrader.py:56) that raised EOFError in the field.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atdd.coach.commands.upgrader import Upgrader

from ._upgrade_unattended_helpers import exploding_input, write_config

pytestmark = [pytest.mark.platform]


@pytest.mark.platform
def test_y007_unit_001_no_tty_pypi_prompt_resolves_without_input(tmp_path, monkeypatch):
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.commands.upgrader.__version__", "3.106.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             return_value=(True, "3.106.0", "4.27.0"),
         ), \
         patch(
             "atdd.coach.commands.upgrader.auto_upgrade",
             return_value=(True, ""),
         ) as mock_upgrade, \
         patch("sys.stdin.isatty", return_value=False), \
         patch("builtins.input", side_effect=exploding_input):
        rc = Upgrader(repo_root=tmp_path).run(yes=False)

    # The defect: today this line is never reached because input() raises first.
    assert rc == 0, f"a no-TTY run must complete, got rc={rc}"
    assert mock_upgrade.call_count == 1, (
        "the resolved confirmation must proceed to the upgrade exactly once, "
        f"got {mock_upgrade.call_count} call(s)"
    )
