# URN: test:integration-hardening:run-upgrade-unattended:Y007-UNIT-002-no-tty-sync-prompt-resolves-without-input
# Acceptance: acc:integration-hardening:Y007-UNIT-002-no-tty-sync-prompt-resolves-without-input
# WMBT: wmbt:integration-hardening:Y007
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""Y007-UNIT-002 — the second prompt is guarded too.

RED Test for acc:integration-hardening:Y007-UNIT-002-no-tty-sync-prompt-resolves-without-input
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:Y007
Purpose: With stdin not a terminal and only a stale local stamp to reconcile,
Upgrader.run() runs sync + init --force without asking 'Proceed? [Y/n]'. There
are two unguarded input() calls in upgrader.py, not one.
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
def test_y007_unit_002_no_tty_sync_prompt_resolves_without_input(tmp_path, monkeypatch):
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    calls = []

    def record(argv, **kwargs):
        calls.append(list(argv))
        return _Ok()

    with patch("atdd.coach.commands.upgrader.__version__", "4.27.0"), \
         patch("atdd.coach.commands.upgrader.run_repo_refresh", side_effect=lambda *_a, **_k: calls.append(["refresh"]) or 0), \
         patch("sys.stdin.isatty", return_value=False), \
         patch("builtins.input", side_effect=exploding_input):
        rc = Upgrader(repo_root=tmp_path).run(yes=False, no_pypi=True)

    assert rc == 0, f"a no-TTY sync run must complete, got rc={rc}"

    # #1820: the refresh is performed in-process. It used to be `atdd sync`
    # followed by `atdd init --force`; the second is forbidden by #793 and, per
    # #1600, returns 1 without bootstrapping anything on an initialised repo.
    joined = [" ".join(c) for c in calls]
    assert any("refresh" in c for c in joined), f"the refresh did not run; calls={joined}"
